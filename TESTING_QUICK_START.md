# 🚀 Quick Start: Test Auto-Retry & Status Reconciliation

**30-Second Setup** → **5-Minute Test** → **Verify Implementation**

---

## ⚡ Fastest Test (2 minutes)

### 1. Open Browser
```
http://localhost:5174
```

### 2. Open Console (F12)
Paste this:
```javascript
console.log('Testing auto-retry...');
```

### 3. Send Message
Type: `"What is 2+2?"`

### 4. Go Offline
DevTools → Network Tab → Select "Offline"

### 5. Watch Magic ✨
- ⏱️ **5 seconds**: First auto-retry
- ⏱️ **15 seconds**: Second auto-retry
- ⏱️ **45 seconds**: Third auto-retry
- 📝 **UI**: "Reconnecting automatically..."

### 6. Go Online
Select "No throttling"

### 7. Verify ✅
- Response continues
- No duplicate message
- No errors in console

**Done!** Auto-retry works! 🎉

---

## 🎯 Quick Console Commands

Open browser console and run:

### Check State
```javascript
// Quick status
responsePhase?.value + ' | ' + autoRetryCount?.value + '/3'

// Full state
console.log({
  phase: responsePhase?.value,
  retries: autoRetryCount?.value,
  error: lastError?.value,
  sessionId: sessionId?.value
})
```

### Watch Real-Time
```javascript
setInterval(() => {
  console.log(`${responsePhase?.value} | ${autoRetryCount?.value}/3`)
}, 2000)
```

### Force Timeout (Testing Only)
```javascript
transitionTo('timed_out')
```

---

## 📋 Full Test Suite (15 minutes)

### Test 1: Auto-Retry ⏱️ 3 min
1. Send message
2. Go offline
3. Watch 3 retries (5s, 15s, 45s)
4. Go online
5. Verify recovery

### Test 2: Status Reconciliation ⏱️ 5 min
1. Start long task
2. Go offline
3. Wait for backend completion
4. Go online + retry
5. Verify instant completion (no flash)

### Test 3: Session Persistence ⏱️ 3 min
1. Start task in Session A
2. Create Session B
3. Verify A continues
4. Return to A
5. Verify resume works

### Test 4: Page Refresh ⏱️ 2 min
1. Start task
2. Press F5
3. Verify no resubmission
4. Verify events resume

### Test 5: Error Display ⏱️ 2 min
1. Exhaust retries
2. Check error notice
3. Verify hint shown
4. Verify retry button

---

## 🛠️ Helper Scripts

### Interactive Test Menu
```bash
./docs/testing/test-auto-retry.sh
```

### Watch Backend Logs
```bash
docker logs -f pythinker-backend-1 | grep -E "(timeout|reconnect|DoneEvent)"
```

### Check Container Status
```bash
docker ps --filter "name=pythinker"
```

---

## ✅ Success Criteria Checklist

- [ ] Auto-retry fires 3 times (5s, 15s, 45s)
- [ ] UI shows "Reconnecting automatically..."
- [ ] Status reconciliation prevents duplicate execution
- [ ] Manual retry cancels auto-retry timer
- [ ] RUNNING sessions continue on navigation
- [ ] Page refresh resumes (no resubmission)
- [ ] Error notices show recovery hints
- [ ] No console errors during tests
- [ ] State machine blocks invalid transitions

---

## 🐛 Common Issues

| Issue | Fix |
|-------|-----|
| Auto-retry not triggering | Check `autoRetryCount.value < 3` |
| Status reconciliation not working | Ensure network online when retrying |
| Events not replaying | Check sessionStorage has lastEventId |
| Multiple retries at once | Manual retry should cancel auto-retry timer |

---

## 📊 Expected Console Logs

### Auto-Retry
```
[AutoRetry] Scheduling retry 1/3 in 5s
[ResponsePhase] timed_out → connecting
SSE connection closed. Reconnecting in 5s...
```

### Status Reconciliation
```
[ResponsePhase] timed_out → connecting
[ResponsePhase] connecting → completing
[ResponsePhase] completing → settled
```

### Page Refresh
```
[RESTORE] Loaded lastEventId from sessionStorage
[RESTORE] Session: <id> Status: running
[RESTORE] No stop flag, auto-resuming session
```

---

## 🎬 Video Tutorial

1. **Record these tests** as you execute them
2. **Share with team** for verification
3. **Document any issues** in TEST_EXECUTION_RESULTS.md

---

## 📞 Need Help?

1. Check `docs/testing/AUTO_RETRY_STATUS_RECONCILIATION_TEST.md` for detailed instructions
2. Run `./docs/testing/test-auto-retry.sh` for interactive guide
3. Paste `docs/testing/browser-test-console.js` in console for utilities

---

**Ready to test?** → Open http://localhost:5174 and start! 🚀
