# PRODUCTION READINESS CHECKLIST

**This bot can go LIVE only after ALL items below are completed and signed off.**

---

## PHASE 1: CRITICAL FIXES (MUST COMPLETE)
**Target:** End of Week 1

### State Management ✓
- [ ] StateTransaction class completed with rollback support
- [ ] Lock acquisition properly handles Windows/Unix
- [ ] Atomic writes use temp-file-then-rename pattern
- [ ] Backup creation tested with simulated crashes
- [ ] Lock timeout tested (what happens after 15 seconds)
- [ ] Concurrent access tested (multiple processes)

**Owner:** ____________________  **Date:** __________

### Capital Calculation ✓
- [ ] Available capital = Total - Positions - Pending - Buffer (NO unrealized P&L)
- [ ] Safety buffer (15%) enforced
- [ ] Pending buy orders properly reserved
- [ ] Fee calculations integrated into position sizing
- [ ] Test: Capital calc with 10 open positions
- [ ] Test: Capital calc with pending orders
- [ ] Test: Over-limit prevention works

**Owner:** ____________________  **Date:** __________

### Duplicate Order Prevention ✓
- [ ] Pending orders saved IMMEDIATELY after place_order()
- [ ] Idempotency check prevents duplicate buys per symbol
- [ ] Crash between place_order() and save: recovery verified
- [ ] Test: 5 programmatic crashes, state verified consistent
- [ ] Broker order reconciliation working

**Owner:** ____________________  **Date:** __________

### Orphaned Position Detection ✓
- [ ] Startup reconciliation with broker positions
- [ ] Auto-close logic for orphaned positions
- [ ] Human verification checkpoint before close
- [ ] Alert on first detection
- [ ] Test: Manually create orphan position, verify detection
- [ ] Test: Close orphan position successfully

**Owner:** ____________________  **Date:** __________

---

## PHASE 2: HIGH-PRIORITY FIXES (MUST COMPLETE)
**Target:** End of Week 2

### Error Recovery & Retry Logic ✓
- [ ] Exponential backoff implemented for API calls
- [ ] Circuit breaker pattern (stop after N failures)
- [ ] Graceful degradation (bot continues without new trades)
- [ ] Connection check at startup
- [ ] Test: Simulate broker down, bot continues
- [ ] Test: Broker comes back, bot resumes trading

**Owner:** ____________________  **Date:** __________

### Price Fetching Fallback Chain ✓
- [ ] Primary: Zerodha Kite API
- [ ] Secondary: yfinance (real-time, not 15min delayed)
- [ ] Tertiary: Cached last-known price (1hr max)
- [ ] Circuit breaker: Stop if >10 consecutive failures
- [ ] Test: Kite down, fallback to yfinance
- [ ] Test: Both down, use cached price

**Owner:** ____________________  **Date:** __________

### Slippage Protection ✓
- [ ] Actual vs planned fill price tracked
- [ ] Alert on slippage > MAX_SLIPPAGE_PCT
- [ ] Limit orders option available (fallback to market if timeout)
- [ ] Aggressive close-out for pending orders >5min
- [ ] Test: Execute with realistic slippage, verify tracking

**Owner:** ____________________  **Date:** __________

### Fee Integration ✓
- [ ] Broker fees calculated for all trades
- [ ] STT, GST, NSE charges included
- [ ] Deducted from position sizing
- [ ] P&L tracking shows net (after-fee) numbers
- [ ] Test: ₹50k trade, verify fee deduction ≈0.035%

**Owner:** ____________________  **Date:** __________

### Notification System ✓
- [ ] Email alerts for critical events
- [ ] Telegram bot for quick checks
- [ ] SMS for kill-switch triggers (optional)
- [ ] Test: Send test alert via email
- [ ] Test: Send test alert via Telegram

**Owner:** ____________________  **Date:** __________

---

## PHASE 3: OPERATIONAL IMPROVEMENTS (MUST COMPLETE)
**Target:** End of Week 3

### Comprehensive Logging ✓
- [ ] Structured JSON logs (not just text)
- [ ] Correlation IDs for transaction tracking
- [ ] Log rotation (50MB files, 30-day retention)
- [ ] Sensitive data redacted (no API keys, passwords)
- [ ] Test: Parse logs programmatically
- [ ] Test: Log rotation works correctly

**Owner:** ____________________  **Date:** __________

### Trade Journaling ✓
- [ ] Every trade logged with entry/exit/P&L
- [ ] Entry timestamp and actual fill time tracked
- [ ] Reason for trade (screener signal)
- [ ] Actual vs planned execution price
- [ ] Export to CSV for analysis
- [ ] Test: Export trades and verify accuracy

**Owner:** ____________________  **Date:** __________

### Real-Time Monitoring ✓
- [ ] REST API for bot state
- [ ] WebSocket feed for real-time updates
- [ ] Web dashboard (even simple HTML)
- [ ] Telegram bot status command
- [ ] Test: Monitor shows accurate state during trading

**Owner:** ____________________  **Date:** __________

### Testing Framework ✓
- [ ] Unit tests for critical functions
- [ ] Integration tests (simulated broker)
- [ ] Stress tests (50+ positions, rapid changes)
- [ ] Recovery tests (crash/disconnect scenarios)
- [ ] Test suite runs before each deployment
- [ ] CI/CD pipeline (GitHub Actions recommended)

**Owner:** ____________________  **Date:** __________

---

## PAPER TRADING VALIDATION (REQUIRED)
**Target:** Week 3-4 (Minimum 1 week)

### Pre-Market Checklist ✓
- [ ] Run daily for 5 trading days in a row
- [ ] Zero crashes (bot runs full market hours)
- [ ] All trades logged correctly
- [ ] P&L tracking accurate to ±0.01%
- [ ] Position limits enforced
- [ ] Kill-switch tested (trigger loss limit)

**Owner:** ____________________  **Date:** __________

### Recovery Scenarios ✓
- [ ] Simulate broker disconnect: Bot should pause, not crash
- [ ] Simulate network timeout: Bot should retry, not exit
- [ ] Simulate invalid screener data: Bot should skip, not crash
- [ ] Simulate negative capital: Bot should stop new trades
- [ ] Simulate stuck pending order: Bot should timeout/close

**Owner:** ____________________  **Date:** __________

### P&L Accuracy ✓
- [ ] Trades matched exactly with broker positions
- [ ] Entry/exit prices verified
- [ ] Fees deducted correctly
- [ ] Realized vs unrealized separated correctly
- [ ] Manual verification against broker statement
- [ ] Accuracy within ₹1 (rounding)

**Owner:** ____________________  **Date:** __________

### Capital Management ✓
- [ ] Starting capital set correctly
- [ ] Available capital calculation verified daily
- [ ] Allocation math checks out (positions + pending + buffer = total)
- [ ] No over-leveraging
- [ ] Safety buffer (15%) never violated

**Owner:** ____________________  **Date:** __________

---

## DEPLOYMENT READINESS (FINAL CHECKS)

### Documentation ✓
- [ ] README with setup instructions
- [ ] Configuration guide (how to change rules)
- [ ] Emergency procedures (how to kill positions)
- [ ] Monitoring guide (what to watch)
- [ ] Troubleshooting guide (common issues)
- [ ] Contact list (broker support, dev, etc.)

**Owner:** ____________________  **Date:** __________

### Backup & Disaster Recovery ✓
- [ ] State files backed up hourly
- [ ] Backup retention policy (30 days min)
- [ ] Recovery tested: restore from backup, state is correct
- [ ] Procedure for restoring from backup documented
- [ ] Test: Corrupt state file, recover from backup

**Owner:** ____________________  **Date:** __________

### Broker API Credentials ✓
- [ ] API credentials stored securely (not in code)
- [ ] Environment variables or secrets manager used
- [ ] Credentials can be rotated without code change
- [ ] Paper trading credentials separate from live
- [ ] Test: Can switch between paper/live with config only

**Owner:** ____________________  **Date:** __________

### Hardware & Infrastructure ✓
- [ ] Dedicated machine/VPS for bot (not laptop)
- [ ] Stable internet connection (99.9% uptime minimum)
- [ ] Power backup (UPS recommended)
- [ ] Daily system monitoring (CPU, RAM, disk)
- [ ] Automatic restart on crash
- [ ] Time sync (NTP) for accurate timestamps

**Owner:** ____________________  **Date:** __________

---

## FINAL SIGN-OFF (Required Before Going Live)

### Code Review ✓
- [ ] All changes reviewed by another developer
- [ ] No critical issues found
- [ ] Reviewer sign-off obtained

**Code Reviewer:** ____________________  
**Date:** __________  
**Sign-off:** ✓ __________

### Broker Account Verification ✓
- [ ] Paper trading verified with actual broker connection
- [ ] Live account opened and verified
- [ ] Live trading enabled (with restrictions)
- [ ] Starting capital verified in account

**Broker:** ____________________  
**Account:** ____________________  
**Date Verified:** __________

### Risk Officer Sign-Off (Recommended) ✓
- [ ] Read entire review document
- [ ] Understands all risks
- [ ] Agrees with mitigation strategies
- [ ] Ready for live trading

**Risk Officer:** ____________________  
**Date:** __________  
**Sign-off:** ✓ __________

### Bot Developer Sign-Off ✓
- [ ] All items above completed
- [ ] Tests passing
- [ ] Code reviewed
- [ ] Ready for production

**Developer:** ____________________  
**Date:** __________  
**Sign-off:** ✓ __________

---

## LIVE TRADING PHASES

### Phase 1: MINIMAL (Week 1)
- **Capital:** ₹5,000 ONLY (not more!)
- **Max Positions:** 1 at a time
- **Max Trade Size:** ₹1,000 per trade
- **Daily P&L Limit:** ±2%
- **Monitoring:** Constant (human present)
- **Duration:** 1 week

✓ All systems stable?  
→ Proceed to Phase 2

❌ Any issues?  
→ Fix immediately, restart Phase 1

---

### Phase 2: CONSERVATIVE (Week 2-3)
- **Capital:** ₹10,000 - ₹25,000
- **Max Positions:** 3 at a time
- **Max Trade Size:** ₹5,000 per trade
- **Daily P&L Limit:** ±2%
- **Monitoring:** Regular (check 3-4x daily)
- **Duration:** 2 weeks

✓ Win rate > 40%?  
✓ P&L positive?  
✓ All systems stable?  
→ Proceed to Phase 3

---

### Phase 3: STANDARD (Week 4+)
- **Capital:** Full account
- **Max Positions:** 5 at a time
- **Daily P&L Limit:** ±2% (or lower)
- **Monitoring:** Daily checks

✓ Consistently profitable?  
✓ Ready for optimization

---

## DOCUMENTATION TO PREPARE

Before going live, have these ready:

1. **Operations Manual**
   - How to start/stop the bot
   - How to check status
   - How to manually close positions
   - Escalation procedures

2. **Troubleshooting Guide**
   - Bot won't start → check logs
   - Positions not executing → check capital/limits
   - Broker connection lost → fallback procedure
   - State corruption → recovery procedure

3. **Incident Response Plan**
   - What to do if bot crashes
   - What to do if broker API down
   - What to do if losing money rapidly
   - Who to contact (support numbers)

4. **Change Log**
   - All code changes made from review
   - Dates and reasons for changes
   - Testing done for each change

---

## GO/NO-GO DECISION

**[ ] GO LIVE** - All boxes checked, signed off, ready for production  
**[ ] NO-GO** - Issues remain, more work needed (list below)

### Outstanding Issues:
```
1. _________________________________
2. _________________________________
3. _________________________________
```

---

**Last Updated:** December 26, 2025  
**Valid Until:** January 31, 2026  
*Checklist must be recertified monthly*

