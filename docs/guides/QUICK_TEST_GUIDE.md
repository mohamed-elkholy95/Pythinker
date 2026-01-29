# Quick Test Guide - Desktop Screenshot Thumbnails

## Prerequisites

Wait for sandbox to finish building:
```bash
docker ps | grep pythinker-sandbox
# Should show "Up X minutes (healthy)"
```

---

## Test 1: Screenshot API (30 seconds)

### Check Availability
```bash
curl http://localhost:8083/api/v1/vnc/screenshot/test
```

**Expected output:**
```json
{
  "available": true,
  "tools": {
    "xwd": true,
    "convert": true,
    "display_99": true
  },
  "message": "Screenshot system ready"
}
```

### Capture Test Screenshot
```bash
curl http://localhost:8083/api/v1/vnc/screenshot -o /tmp/test_screenshot.jpg
open /tmp/test_screenshot.jpg  # macOS
```

**Expected:** Should see a screenshot of the sandbox desktop

---

## Test 2: End-to-End (2 minutes)

### 1. Open Frontend
```
http://localhost:5174
```

### 2. Start New Chat
Click "New Chat" or press Cmd+K

### 3. Run Simple Command
```
Run 'ls -la' to list files
```

### 4. Watch TaskProgressBar

**What to look for:**
- ✅ Small thumbnail appears above progress bar
- ✅ Shows terminal/desktop screenshot
- ✅ Updates as task progresses
- ✅ No "No preview" placeholder

### 5. Click Thumbnail
Should expand to show full task details

---

## Test 3: Different Tool Types (5 minutes)

Try these commands and verify screenshots:

### Shell Commands
```
Run 'python --version'
Run 'pwd'
Run 'echo "Hello World"'
```
**Expected:** Desktop screenshots showing terminal output

### Code Execution
```
Write a Python script that prints "Hello" and run it
```
**Expected:** Screenshot after code execution

### File Operations (No Screenshot)
```
Read the README file
```
**Expected:** No thumbnail (file operations don't need screenshots)

---

## Debugging

### Issue: "available": false

```bash
# Check if tools are installed
docker exec pythinker-sandbox-1 which xwd
docker exec pythinker-sandbox-1 which convert

# If not found, rebuild sandbox
docker-compose -f docker-compose-development.yml up -d --build sandbox
```

### Issue: No thumbnails appearing

1. **Check backend logs:**
   ```bash
   docker logs pythinker-backend-1 | grep -i screenshot
   ```

2. **Check browser console:**
   - Open DevTools (F12)
   - Look for errors in console
   - Check Network tab for SSE events

3. **Verify tool_content:**
   ```bash
   docker logs pythinker-backend-1 | grep tool_content
   ```
   Should show `screenshot` field with data URL

### Issue: Thumbnails too large/slow

Adjust in `backend/app/domain/services/agents/base.py`:
```python
response = await self.sandbox.get_screenshot(
    quality=60,   # Lower (default: 75)
    scale=0.3,    # Smaller (default: 0.5)
)
```

---

## Performance Check

### Expected Metrics:
- Screenshot capture: ~100-200ms
- Image size: ~20-40KB (JPEG, 50% scale)
- Total overhead per command: ~150-300ms

### Monitor Performance:
```bash
# Backend timing logs
docker logs pythinker-backend-1 | grep "Screenshot capture"

# Watch network traffic
# Open DevTools → Network tab → Filter by SSE
# Check size of events with screenshots
```

---

## Success Indicators

✅ **Everything working if:**
1. Screenshot test endpoint returns `"available": true`
2. Thumbnail appears in TaskProgressBar after commands
3. Thumbnail shows actual desktop/terminal content
4. No errors in browser console
5. Performance impact < 300ms per command

❌ **Issues to investigate if:**
1. Test endpoint returns `"available": false`
2. Thumbnails never appear
3. "No preview" still shows
4. Console shows errors
5. Commands take >1s longer than before

---

## Quick Fixes

### Restart Everything
```bash
cd /Users/panda/Desktop/Projects/pythinker
./dev.sh restart
```

### Rebuild Sandbox Only
```bash
docker-compose -f docker-compose-development.yml up -d --build sandbox
```

### Check Service Health
```bash
docker ps
docker logs pythinker-backend-1 --tail 50
docker logs pythinker-sandbox-1 --tail 50
```

---

## Advanced Testing

### Test Different Image Formats
```bash
# JPEG (default, smaller)
curl "http://localhost:8083/api/v1/vnc/screenshot?format=jpeg" -o test.jpg

# PNG (larger, higher quality)
curl "http://localhost:8083/api/v1/vnc/screenshot?format=png" -o test.png
```

### Test Different Quality/Scale
```bash
# Lowest quality/size
curl "http://localhost:8083/api/v1/vnc/screenshot?quality=50&scale=0.3" -o tiny.jpg

# Highest quality/size
curl "http://localhost:8083/api/v1/vnc/screenshot?quality=100&scale=1.0" -o large.jpg

# Compare sizes
ls -lh *.jpg
```

### Monitor Real-Time
```bash
# Terminal 1: Watch backend logs
docker logs -f pythinker-backend-1 | grep screenshot

# Terminal 2: Run commands in frontend
# You'll see screenshot captures in real-time
```

---

## Next Steps After Successful Test

1. ✅ Verify thumbnails work for multiple commands
2. 📝 Test with different tool types (shell, code, browser)
3. 🎨 Optional: Add live VNC in expanded view (see HYBRID_IMPLEMENTATION_COMPLETE.md)
4. 📊 Monitor performance in production
5. 💾 Consider adding screenshot caching

---

## Get Help

If issues persist:

1. **Check all documentation:**
   - `HYBRID_IMPLEMENTATION_COMPLETE.md` - Full implementation guide
   - `HYBRID_THUMBNAIL_APPROACH.md` - Architecture details
   - `THUMBNAIL_PREVIEW_FIX.md` - Why it was needed

2. **Collect debug info:**
   ```bash
   docker logs pythinker-backend-1 > backend.log
   docker logs pythinker-sandbox-1 > sandbox.log
   curl http://localhost:8083/api/v1/vnc/screenshot/test > test.json
   ```

3. **Check git status:**
   ```bash
   git status
   git diff
   ```

---

**Ready to test?** Start with Test 1, then Test 2. Should take ~3 minutes total.
