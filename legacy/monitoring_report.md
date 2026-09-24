# Denaro Trading Bot Status Report

## Overview
This report summarizes the current status of Denaro trading bots across the three monitored nodes: mc2, nuvola, and MARCODG1.

## Node Status

### mc2
- **PID Status**: Not running (no denaro process found)
- **Error Logs**: No logs directory found
- **Database**: trades.db not found

### nuvola
- **PID Status**: No denaro processes found
- **Error Logs**: No logs directory found
- **Database**: trades.db not found

### MARCODG1
- **PID Status**: Not running (no denaro process found)
- **Error Logs**: No logs directory found
- **Database**: trades.db not found

## Summary
All nodes show that the Denaro trading bots are not currently running. No trade database (trades.db) exists on any node. The logs directories are missing on all nodes.

## Recommendations
1. Verify the bots are properly configured for auto-start
2. Check if the denaro script files exist and have proper execute permissions
3. Ensure the logging directories are created and writable
4. Check network connectivity for Binance API access
5. Review and re-enable systemd services or screen sessions as appropriate
