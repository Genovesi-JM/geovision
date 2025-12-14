# VS Code Integration for GeoVision Chatbot

## Overview

The GeoVision chatbot (GAIA Assistant) now includes VS Code connection detection and integration features. This allows users to know when they're accessing the application through VS Code's webview or Live Preview extension.

## Features

### 1. **Automatic VS Code Detection**

The chatbot automatically detects if the page is being viewed within VS Code by checking:
- User agent strings containing 'vscode'
- Window context (embedded in VS Code webview)
- Electron environment indicators

### 2. **Visual Status Indicator**

When connected to VS Code, a status badge appears in the chatbot header showing:
- ⚡ Lightning icon (animated pulse effect)
- "VS Code" text label
- Blue themed styling to match VS Code's color scheme

### 3. **Contextual Greeting**

The chatbot's initial greeting message adapts based on the connection status:
- **When connected**: "Olá 👋 Sou o assistente da GeoVision. Estou conectado ao VS Code! ⚡"
- **When not connected**: Standard greeting without VS Code mention

### 4. **Smart Question Handling**

Users can ask about VS Code connection status using natural language:
- "are you connected to vs code?"
- "estás conectado ao code?"
- "vs code connection"
- "connected to code"

The assistant will respond with:
- Connection status confirmation
- Instructions on how to connect if not already connected
- Information about the integration benefits

### 5. **Backend Integration**

Connection status is sent with API requests via the `vscode_connected` parameter, allowing:
- Analytics tracking of VS Code usage
- Conditional feature enabling
- User experience insights

## Usage

### Testing the Feature

1. **In a Regular Browser**:
   - Open `index.html` in Chrome, Firefox, Safari, etc.
   - The chatbot will not show the VS Code indicator
   - Asking about VS Code will return instructions on how to connect

2. **In VS Code**:
   - Install "Live Preview" or "Live Server" extension
   - Right-click on `index.html` and select "Open with Live Server" or "Show Preview"
   - The chatbot will show the VS Code indicator (⚡ VS Code)
   - The greeting will mention the connection

### Ask the Chatbot

Try these questions:
```
- are you connected to the vs code?
- estás conectado ao VS Code?
- VS Code connection status
- connected to code?
```

## Technical Implementation

### Detection Function (`isInVSCode`)

```javascript
function isInVSCode() {
  // Check for VS Code specific user agents or window properties
  const userAgent = navigator.userAgent.toLowerCase();
  const isVSCodeUA = userAgent.includes('vscode');
  
  // Try to check parent window protocol (wrapped in try-catch for cross-origin safety)
  let isVSCodeWindow = false;
  try {
    if (window.parent && window.parent !== window) {
      isVSCodeWindow = window.parent.location.protocol === 'vscode-webview:';
    }
  } catch (e) {
    // Cross-origin access denied - not a VS Code webview
    isVSCodeWindow = false;
  }
  
  const isElectron = userAgent.includes('electron');
  
  // VS Code embeds pages in webviews with specific characteristics
  return isVSCodeUA || isVSCodeWindow || (isElectron && window.parent !== window);
}

// Pre-compiled regex patterns for VS Code question detection (performance optimization)
const VSCODE_QUESTION_PATTERNS = [
  /vs code/i,
  /vscode/i,
  /visual studio code/i,
  /conectado.{0,20}(vs code|vscode)/i,
  /connected.{0,20}(vs code|vscode)/i,
  /(vs code|vscode).{0,20}(conectado|connected)/i
];
```

**Key Features of the Detection:**
- **Cross-origin safe**: Uses try-catch to prevent errors when accessing parent window
- **Multi-factor detection**: Checks user agent, window context, and Electron environment
- **Performance optimized**: Pre-compiled regex patterns for question detection

### CSS Styling

The VS Code status indicator includes:
- Subtle blue background with transparency
- Border matching VS Code theme
- Animated pulse effect on the lightning icon
- Responsive sizing

### Files Modified

- `assets/js/chatbot.js` - Detection logic and UI updates
- `assets/css/chatbot.css` - Status indicator styling

## Future Enhancements

Potential improvements for the VS Code integration:

1. **VS Code Extension**: Create a dedicated VS Code extension for deeper integration
2. **Command Palette**: Add commands accessible from VS Code's command palette
3. **Workspace Integration**: Access workspace files and configurations
4. **IntelliSense**: Provide code completion for GeoVision-specific syntax
5. **Debugging**: Integrate with VS Code's debugging tools
6. **Terminal Integration**: Execute commands directly from the chatbot

## Browser Compatibility

The detection works across:
- ✅ VS Code Live Preview
- ✅ VS Code Live Server
- ✅ VS Code Simple Browser
- ✅ Chrome, Firefox, Safari (shows not connected)
- ✅ Edge, Opera (shows not connected)

## Support

For issues or questions about the VS Code integration, please check:
- The chatbot responds to VS Code connection queries
- Browser console for any JavaScript errors
- VS Code extensions are properly installed and active
