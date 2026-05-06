#!/usr/bin/env python3
"""Denaro Host Sentry — monitor grid bot, restart on failure"""
import subprocess, time, sys

BOT_NAME = 'grid_bot_v3.py'
CHECK_INTERVAL = 60

def is_running():
    r = subprocess.run(['pgrep', '-f', BOT_NAME], capture_output=True, text=True)
    return bool(r.stdout.strip())

def restart():
    subprocess.run(['pkill', '-f', BOT_NAME])
    time.sleep(2)
    subprocess.Popen(
        ['/home/marco/denaro/venv/bin/python3', BOT_NAME],
        cwd='/home/marco/denaro',
        stdout=open('/home/marco/denaro/grid.log', 'a'),
        stderr=subprocess.STDOUT
    )

if __name__ == '__main__':
    print('Host Sentry started, PID ' + str(len(sys.argv)))
    while True:
        started = False
        if not is_running():
            print('Bot not running, restarting...')
            restart()
            started = True
        else:
            pass
        time.sleep(30 if started else CHECK_INTERVAL)
