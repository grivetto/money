#!/usr/bin/env python3
import os
import asyncio
import json
import aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv('/home/sergio/.openclaw/workspace/denaro/.env')

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8028848403:***')


async def get_nuvola_data():
    """Legge dati dal Grid Bot su NUVOLA"""
    try:
        with open('/home/sergio/.openclaw/workspace/denaro/REALISTIC_GRID.log', 'r') as f:
            lines = f.readlines()[-20:]
        investment = 35
        for line in reversed(lines):
            if 'Investimento:' in line:
                try:
                    investment = float(line.split('\u20ac')[1].split()[0])
                except Exception:
                    pass
                break
        for line in reversed(lines):
            if 'Grid piazzato:' in line:
                try:
                    num = line.split('Grid piazzato:')[1].split()[0]
                    return {'investment': investment, 'orders': num, 'status': 'running'}
                except Exception:
                    pass
                break
        return {'investment': investment, 'orders': '3', 'status': 'running'}
    except Exception as e:
        return {'investment': 35, 'orders': '?', 'status': f'error: {e}'}


async def get_mc2_data():
    """Legge dati dal Rebound Sniper su MC2"""
    try:
        with open('/home/sergio/denaro/status/positions_real.json', 'r') as f:
            positions = json.load(f)
        with open('/home/sergio/denaro/logs/rebound_real.log', 'r') as f:
            lines = f.readlines()[-30:]
        active = len([p for p in positions.values() if p.get('status') in ['hold', 'pending_buy']])
        pending_sell = len([p for p in positions.values() if p.get('status') == 'pending_sell'])
        last_trade = None
        for line in reversed(lines):
            if 'BUY' in line and 'EXECUTED' in line:
                last_trade = 'BUY ' + line.split('BUY')[1].strip()[:30]
                break
            if 'CLOSED' in line and 'PNL' in line:
                last_trade = line.split('CLOSED')[1].strip()[:40]
                break
        return {
            'active_positions': active,
            'pending_sell': pending_sell,
            'last_trade': last_trade or 'No trades yet',
            'status': 'running'
        }
    except Exception as e:
        return {'active_positions': 0, 'pending_sell': 0, 'last_trade': 'No data', 'status': 'waiting'}


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /status - mostra stato reale"""
    nuvola = await get_nuvola_data()
    mc2 = await get_mc2_data()
    message = (
        f"\U0001f680 *DENARO SYSTEM \u2014 REAL DATA*\n\n"
        f"\U0001f4b0 *Capitale Allocato*\n"
        f"\u2022 NUVOLA (Grid): \u20ac{nuvola['investment']}\n"
        f"\u2022 MC2 (Rebound): Risk 0.2% BTC/trade\n\n"
        f"\U0001f4ca *NUVOLA \u2014 Grid BTC/EUR*\n"
        f"Status: {nuvola['status']}\n"
        f"Ordini aperti: {nuvola['orders']} BUY\n"
        f"Attesa: BTC scenda a ~\u20ac57k\n\n"
        f"\U0001f3af *MC2 \u2014 Rebound Sniper*\n"
        f"Status: {mc2['status']}\n"
        f"Posizioni attive: {mc2['active_positions']}\n"
        f"In chiusura: {mc2['pending_sell']}\n"
        f"Ultimo: {mc2['last_trade']}\n\n"
        f"\u23f0 Aggiornato: {datetime.now().strftime('%H:%M:%S')}"
    )
    keyboard = [
        [InlineKeyboardButton('\U0001f504 Aggiorna', callback_data='refresh')],
        [InlineKeyboardButton('\U0001f4c8 MC2 Log', callback_data='mc2_log'),
         InlineKeyboardButton('\U0001f4ca NUVOLA Log', callback_data='nuvola_log')]
    ]
    await update.message.reply_text(
        message,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'refresh':
        await status(update, context)
    elif query.data == 'mc2_log':
        try:
            with open('/home/sergio/denaro/logs/rebound_real.log', 'r') as f:
                lines = f.readlines()[-15:]
            log_text = ''.join(lines)[-3500:]
            await query.edit_message_text(
                f'*\u2b50 MC2 Log (ultime righe):*\n\n{log_text}',
                parse_mode='Markdown'
            )
        except Exception as e:
            await query.edit_message_text(f'Errore lettura log: {e}')
    elif query.data == 'nuvola_log':
        try:
            with open('/home/sergio/.openclaw/workspace/denaro/REALISTIC_GRID.log', 'r') as f:
                lines = f.readlines()[-15:]
            log_text = ''.join(lines)[-3500:]
            await query.edit_message_text(
                f'*\u2b50 NUVOLA Log (ultime righe):*\n\n{log_text}',
                parse_mode='Markdown'
            )
        except Exception as e:
            await query.edit_message_text(f'Errore lettura log: {e}')


async def profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /profit - calcola P&L"""
    try:
        with open('/home/sergio/denaro/status/positions_real.json', 'r') as f:
            positions = json.load(f)
        total_pnl = 0.0
        closed = [p for p in positions.values() if p.get('status') == 'closed']
        for p in closed:
            pnl = p.get('pnl', 0)
            if isinstance(pnl, (int, float)):
                total_pnl += pnl
        active = len([p for p in positions.values() if p.get('status') in ['hold', 'pending_buy']])
        try:
            with open('/home/sergio/denaro/drawdown.json', 'r') as f:
                dd = json.load(f)
            peak = dd.get('peak', 500.0)
            current = dd.get('current', 500.0)
            max_dd = dd.get('max_drawdown', 0.0)
        except Exception:
            peak = current = 500.0
            max_dd = 0.0
        message = (
            f"\U0001f4ca *PROFIT REPORT*\n\n"
            f"Posizioni chiuse: {len(closed)}\n"
            f"Posizioni attive: {active}\n"
            f"P&L totale: {total_pnl:+.2f} EUR\n\n"
            f"Picco: \u20ac{peak:.2f}\n"
            f"Attuale: \u20ac{current:.2f}\n"
            f"Max Drawdown: {max_dd:.2f}%"
        )
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f'Errore: {e}')


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('status', status))
    app.add_handler(CommandHandler('profit', profit))
    app.add_handler(CallbackQueryHandler(button))
    print('\U0001f680 Telegram Bot avviato')
    app.run_polling()


if __name__ == '__main__':
    main()