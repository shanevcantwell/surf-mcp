# Fara Test Harness - Quick Reference

```
+------------------------------------------------------------------+
|                     COMMAND SYNTAX                                |
+------------------------------------------------------------------+
|                                                                  |
|  LOCATE       locate "description"                               |
|               Find element, show coordinates + confidence        |
|                                                                  |
|  CLICK        click "description"                                |
|               Click element by natural language                  |
|                                                                  |
|  TYPE         type "description" text to enter                   |
|               Type into field (clears first by default)          |
|                                                                  |
|  NAVIGATE     goto https://example.com                           |
|               Navigate to URL                                    |
|                                                                  |
|  SCROLL       scroll up | scroll down                            |
|               Scroll page by viewport height                     |
|                                                                  |
+------------------------------------------------------------------+
```

## Examples

| Command | What it does |
|---------|--------------|
| `locate "the search button"` | Find and mark the search button |
| `click "Sign in"` | Click the sign in link/button |
| `type "email input" user@example.com` | Type email into the email field |
| `goto https://gemini.google.com` | Navigate to Gemini |
| `scroll down` | Scroll down one viewport |

## Visual Overlay

When you use `locate`, a red target appears on the screenshot:
- **Red dot**: Exact coordinates Fara identified
- **Crosshairs**: Visual guide for precision
- **Confidence**: Score (0.0-1.0) showing model certainty

## Session Persistence

- **Storage state** is saved when you disconnect
- Cookies and localStorage are preserved
- Reconnecting restores your logged-in sessions

## Tips

1. **Be specific**: "the blue Submit button" > "submit"
2. **Use visual cues**: "the hamburger menu icon in the top right"
3. **Reference text**: "the link that says 'Learn more'"
4. **Locate first**: Use `locate` to verify before `click`

---

```
  Run:  streamlit run app.py
  Requires: LM Studio with Fara model loaded
```
