# Test Guide - New Browser Features

## ✅ All Containers Ready!

All services are running with the new automatic browser behavior and browser-use integration:

```
✅ Backend (port 8000) - Running
✅ Frontend (port 5174) - Running
✅ Sandbox (port 8083) - Running
✅ MongoDB, Redis, Qdrant - Running
✅ VNC Services:
   - Xvfb (display :1) - Running
   - x11vnc (port 5900) - Running
   - websockify (port 5901) - Running
   - Chrome - Running
```

---

## 🧪 Test Scenarios

### **Test 1: Automatic Scroll + Extract (Single Navigation)**

**What to test:** The new auto-scroll and auto-extract behavior

**Steps:**
1. Open frontend at http://localhost:5174
2. Create new chat session
3. Ask: **"Go to example.com and tell me what's on the page"**

**Expected behavior:**
- ✅ Agent calls `browser_navigate("https://example.com")` ONCE
- ✅ Page automatically scrolls (visible in VNC)
- ✅ Content automatically extracted
- ✅ Agent responds immediately with page content
- ✅ NO additional `browser_view` or `browser_scroll` calls

**Old behavior (before):**
```
browser_navigate → browser_view → browser_scroll → browser_view
(4 tool calls, 15 seconds)
```

**New behavior (now):**
```
browser_navigate (returns everything)
(1 tool call, 5 seconds)
```

---

### **Test 2: Autonomous Task - Product Research**

**What to test:** The new `browser_autonomous_task` tool

**Steps:**
1. Ask: **"Search Google for Python tutorials and tell me what the top result is"**

**Expected behavior:**
- ✅ Agent calls `browser_autonomous_task(task="Search Google for Python tutorials, visit top result, summarize", max_steps=20)`
- ✅ Watch VNC - agent autonomously:
  1. Navigates to Google
  2. Types "Python tutorials" in search box
  3. Clicks search button
  4. Clicks on top result
  5. Scrolls to read content
  6. Extracts key information
- ✅ Returns comprehensive summary

**Watch VNC at:** Open "Pythinker's Computer" panel to see real-time autonomous browsing!

---

### **Test 3: Autonomous Task - Form Filling**

**What to test:** Autonomous form filling

**Steps:**
1. Ask: **"Go to httpbin.org/forms/post and fill out the form with test data"**

**Expected behavior:**
- ✅ Agent uses `browser_autonomous_task`
- ✅ Autonomously:
  1. Navigates to form page
  2. Fills customer name field
  3. Fills telephone field
  4. Fills email field
  5. Selects size from dropdown
  6. Clicks submit button
- ✅ Returns submission confirmation

---

### **Test 4: Autonomous Task - Comparison Shopping**

**What to test:** Complex multi-step autonomous workflow

**Steps:**
1. Ask: **"Search Amazon for wireless mouse and show me the top 3 products with 4+ stars"**

**Expected behavior:**
- ✅ Agent uses `browser_autonomous_task` with higher max_steps
- ✅ Autonomously:
  1. Navigates to Amazon
  2. Searches for "wireless mouse"
  3. Applies 4+ stars filter
  4. Scrolls through results
  5. Extracts top 3 product names, prices, ratings
- ✅ Returns structured comparison

---

### **Test 5: VNC Visibility**

**What to test:** All browser actions are visible in VNC

**Steps:**
1. Open "Pythinker's Computer" panel in frontend
2. Run any of the above tests
3. Watch the VNC viewer

**Expected behavior:**
- ✅ See browser window
- ✅ See automatic scrolling (Test 1)
- ✅ See autonomous typing, clicking, navigation (Tests 2-4)
- ✅ See page loads, form fills, searches in real-time
- ✅ Like watching a human use the browser!

---

## 🔍 What to Look For

### **Performance Improvements**

| Metric | Old | New | Look For |
|--------|-----|-----|----------|
| Tool Calls | 3-4 calls | 1 call | Check agent logs - should see fewer tool calls |
| Response Time | 10-15 sec | 3-5 sec | Time from question to answer |
| VNC Actions | Manual steps | Smooth auto-scroll | Watch VNC during navigation |

### **Backend Logs**

Watch for these log messages:
```
✅ "Auto-scrolled page to load lazy content"
✅ "Auto-extracted content (XXXX chars)"
✅ "Starting autonomous task (max_steps=XX): [task description]"
✅ "Autonomous task completed in X steps"
```

Check logs:
```bash
docker logs pythinker-backend-1 --tail=50 -f
```

### **Sandbox Logs**

Watch for browser-use activity:
```bash
docker logs pythinker-sandbox-1 --tail=50 -f
```

---

## 🐛 Troubleshooting

### **Issue: "browser-use library not installed"**

**Fix:**
```bash
docker-compose -f docker-compose-development.yml build backend sandbox
docker-compose -f docker-compose-development.yml up -d
```

### **Issue: Autonomous task fails**

**Check:**
1. Is task description clear and specific?
2. Is max_steps sufficient? (Try increasing to 30-40 for complex tasks)
3. Check backend logs for errors

**Example of good task:**
```
"Search Amazon for 'mechanical keyboards', filter by Prime and 4+ stars, extract name and price for top 3"
```

**Example of bad task:**
```
"Find keyboards"  # Too vague
```

### **Issue: VNC not showing browser**

**Check:**
1. VNC services running: `docker exec pythinker-sandbox-1 supervisorctl status`
2. All should show RUNNING:
   - xvfb
   - x11vnc
   - websockify
   - chrome

**Restart sandbox:**
```bash
docker-compose -f docker-compose-development.yml restart sandbox
```

---

## 📊 Success Criteria

### **Test 1 (Auto-scroll + Extract):**
- ✅ Single `browser_navigate` call
- ✅ Content returned immediately
- ✅ No manual scroll/view calls
- ✅ Response in < 5 seconds

### **Test 2-4 (Autonomous Tasks):**
- ✅ Agent uses `browser_autonomous_task`
- ✅ All actions visible in VNC
- ✅ Task completes successfully
- ✅ Comprehensive results returned

### **Overall:**
- ✅ Faster responses
- ✅ Fewer tool calls
- ✅ More engaging (watch VNC!)
- ✅ Better results

---

## 📝 Example Test Session

**User:** "Search Google for Python tutorials and summarize the top result"

**Expected Agent Response:**
```
I'll search Google for Python tutorials and summarize the top result for you.

[Uses browser_autonomous_task tool]

After searching Google for "Python tutorials" and visiting the top result
(python.org/tutorials), here's the summary:

The official Python tutorial provides:
- Getting started with Python basics
- Installing Python and setting up development environment
- Interactive interpreter introduction
- Basic syntax and data structures
- Functions and modules
- Standard library overview

The tutorial is designed for beginners and covers fundamental concepts
with hands-on examples.
```

**What you should see in VNC:**
1. Browser opens Google
2. Types "Python tutorials"
3. Clicks search
4. Clicks top result
5. Scrolls through page
6. All happening automatically!

---

## 🎉 Ready to Test!

**Quick Start:**
1. Open http://localhost:5174
2. Create new chat
3. Try Test 1 first (simplest)
4. Then try Test 2 (autonomous)
5. Watch VNC panel for all tests!

**Have fun testing the new autonomous browser! 🚀**
