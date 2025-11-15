# Files System - WebDAV Sync Setup

## Overview

The Files system now includes WebDAV support, enabling Dropbox-like desktop file synchronization. This allows you to mount your Files storage as a network drive on Windows, macOS, or Linux, with full offline read/write capabilities.

**WebDAV Endpoint**: `https://rm.swhgrp.com/files/webdav/`

## Features

- **Offline Access**: Files sync to your computer for offline work
- **Two-Way Sync**: Changes on desktop automatically sync to server
- **Portal SSO**: Uses Portal authentication (same login as web interface)
- **User Isolation**: Each user only sees their own files
- **Large File Support**: Up to 10GB file uploads
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Desktop Clients                          │
│  (Mountain Duck, RaiDrive, Finder, Windows Explorer)        │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebDAV Protocol (HTTPS)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Nginx Reverse Proxy                       │
│  - HTTPS termination (port 443)                             │
│  - Portal SSO auth check                                     │
│  - WebDAV header passthrough                                 │
│  - 10GB max upload size                                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP (Docker network)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Files FastAPI App (files-app:8000)             │
│  - Mounted at /webdav via WSGIMiddleware                    │
│  - Auto-discovery endpoint /.well-known/webdav              │
└──────────────────────────┬──────────────────────────────────┘
                           │ WSGI
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   WsgiDAV Server (v4.3.0)                   │
│  - PortalAuthDomainController                               │
│  - UserIsolatedFilesystemProvider                           │
│  - Property manager (file metadata)                          │
│  - Lock manager (concurrent access)                          │
└──────────────────────────┬──────────────────────────────────┘
                           │ Filesystem
                           ▼
┌─────────────────────────────────────────────────────────────┐
│            User Storage (/app/storage/user_2/)              │
│  - Documents/                                                │
│  - Downloads/                                                │
│  - Pictures/                                                 │
│  - etc.                                                      │
└─────────────────────────────────────────────────────────────┘
```

## Setup Instructions

### Option 1: Mountain Duck (Recommended - macOS & Windows)

**Best for**: Users who want the closest Dropbox-like experience

**Download**: https://mountainduck.io/ (Free trial, $39 license)

#### Setup Steps:

1. **Install Mountain Duck**
   - Download and install from mountainduck.io
   - Launch Mountain Duck

2. **Add Bookmark**
   - Click Mountain Duck icon in system tray/menu bar
   - Click "+" to add new bookmark
   - Select "WebDAV (HTTPS)"

3. **Configure Connection**
   ```
   Server: rm.swhgrp.com
   Port: 443
   Path: /files/webdav/andy
   Username: andy
   Password: [Your Portal password]
   ```

4. **Advanced Settings** (Optional)
   - Enable "Connect on system startup"
   - Enable "Save password in keychain"
   - Set "Default protocol" to "WebDAV (HTTPS)"

5. **Connect**
   - Click "Connect"
   - Files appear as network drive in Finder/Explorer
   - Drag files to/from drive just like Dropbox

**Features**:
- Smart sync (only downloads files when accessed)
- Offline mode support
- File versioning
- Status icons showing sync state
- Background sync

---

### Option 2: RaiDrive (Windows Only - FREE)

**Best for**: Windows users who want a free solution

**Download**: https://www.raidrive.com/download

#### Setup Steps:

1. **Install RaiDrive**
   - Download and install from raidrive.com
   - Launch RaiDrive

2. **Add Drive**
   - Click "Add" button
   - Select "WebDAV"

3. **Configure Connection**
   ```
   Address: https://rm.swhgrp.com/files/webdav/andy
   Drive: [Choose drive letter, e.g., Z:]
   Authentication: Basic
   Username: andy
   Password: [Your Portal password]
   ```

4. **Advanced Options**
   - Check "Reconnect at logon"
   - Check "Read only" if you only need read access

5. **Connect**
   - Click "OK"
   - Drive appears in Windows Explorer
   - Access files like any local drive

---

### Option 3: Native macOS Finder

**Best for**: macOS users who want a free, built-in solution

#### Setup Steps:

1. **Open Finder**
   - Press `Cmd + K` (or Go → Connect to Server)

2. **Enter Server Address**
   ```
   https://rm.swhgrp.com/files/webdav/andy
   ```

3. **Click Connect**
   - Enter username: `andy`
   - Enter password: [Your Portal password]
   - Check "Remember this password in my keychain"

4. **Access Files**
   - Server mounts as network drive
   - Appears in Finder sidebar under "Locations"
   - Drag files to/from drive

**Limitations**:
- No smart sync (downloads all files)
- Slower than Mountain Duck
- Must reconnect after restart

---

### Option 4: Windows Native (Windows 10/11)

**Best for**: Windows users who want a free, built-in solution

#### Setup Steps:

1. **Open File Explorer**
   - Right-click "This PC"
   - Select "Map network drive"

2. **Configure Drive**
   - Drive letter: [Choose, e.g., Z:]
   - Folder: `https://rm.swhgrp.com/files/webdav/andy`
   - Check "Reconnect at sign-in"

3. **Enter Credentials**
   - Username: `andy`
   - Password: [Your Portal password]
   - Check "Remember my credentials"

4. **Access Files**
   - Drive appears in "This PC"
   - Use like any local drive

**Limitations**:
- Windows WebDAV has 50MB default file size limit
- May require registry edit for larger files
- Slower than third-party clients

**Fix for Large Files** (>50MB):
```powershell
# Run as Administrator
reg add HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\WebClient\Parameters /v FileSizeLimitInBytes /t REG_DWORD /d 0xffffffff
net stop webclient
net start webclient
```

---

### Option 5: Linux (davfs2)

**Best for**: Linux users

#### Setup Steps:

1. **Install davfs2**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install davfs2

   # Fedora/RHEL
   sudo dnf install davfs2

   # Arch
   sudo pacman -S davfs2
   ```

2. **Create Mount Point**
   ```bash
   sudo mkdir -p /mnt/rm-files
   ```

3. **Add to /etc/fstab** (for auto-mount)
   ```bash
   sudo nano /etc/fstab
   ```

   Add line:
   ```
   https://rm.swhgrp.com/files/webdav/andy /mnt/rm-files davfs user,noauto,uid=1000,gid=1000 0 0
   ```

4. **Add Credentials**
   ```bash
   nano ~/.davfs2/secrets
   ```

   Add line:
   ```
   https://rm.swhgrp.com/files/webdav/andy andy [your-password]
   ```

   Set permissions:
   ```bash
   chmod 600 ~/.davfs2/secrets
   ```

5. **Mount**
   ```bash
   mount /mnt/rm-files
   ```

6. **Access Files**
   ```bash
   cd /mnt/rm-files
   ls -la
   ```

---

## Authentication

### Portal SSO Integration

WebDAV uses the same Portal authentication as the web interface:

1. **X-Remote-User Header** (Production)
   - Nginx verifies Portal session cookie
   - Adds `X-Remote-User` header to WebDAV requests
   - WebDAV server trusts this header

2. **HTTP Basic Auth** (Fallback)
   - For testing or direct access
   - Username: Portal username (e.g., `andy`)
   - Password: Portal password

### Security

- All traffic over HTTPS (TLS 1.2/1.3)
- Portal session cookies (secure, httponly)
- User isolation (users can only access their own files)
- Same permissions as web interface

---

## Usage Examples

### Uploading Files

1. **Mountain Duck / RaiDrive**
   - Drag files from local folder to mounted drive
   - Files automatically upload in background
   - Status icon shows sync progress

2. **macOS Finder / Windows Explorer**
   - Copy/paste files to network drive
   - Wait for transfer to complete

3. **Command Line** (Linux)
   ```bash
   cp ~/Documents/report.pdf /mnt/rm-files/Documents/
   ```

### Creating Folders

1. **GUI Clients**
   - Right-click in mounted drive → New Folder
   - Same as local filesystem

2. **Command Line**
   ```bash
   mkdir /mnt/rm-files/Projects/NewProject
   ```

### Downloading Files

1. **Smart Sync Clients** (Mountain Duck)
   - Files download on-demand when opened
   - Recently used files cached locally

2. **Traditional Clients**
   - Copy files from network drive to local folder
   - Or open directly from network drive

### Offline Access

**Mountain Duck**:
1. Right-click file/folder
2. Select "Make Available Offline"
3. Files sync to local cache
4. Changes sync when back online

---

## Troubleshooting

### Connection Refused / 401 Unauthorized

**Problem**: Can't connect to WebDAV server

**Solutions**:
1. Verify you're logged into Portal at https://rm.swhgrp.com/portal/
2. Check username/password are correct
3. Try logging out and back into Portal
4. Clear browser cookies and re-login

### Files Not Syncing

**Problem**: Changes not appearing on other devices

**Solutions**:
1. Check internet connection
2. Verify client is connected (not offline mode)
3. Check for file conflicts (client usually prompts)
4. Restart WebDAV client

### Slow Performance

**Problem**: File operations are slow

**Solutions**:
1. Use smart sync client (Mountain Duck) instead of native clients
2. Check network speed (WebDAV is bandwidth-dependent)
3. Avoid opening large files directly from network drive
4. Copy large files to local disk before editing

### Large Files Won't Upload

**Problem**: Files >50MB fail to upload (Windows only)

**Solution**: Increase Windows WebDAV file size limit
```powershell
# Run as Administrator
reg add HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\WebClient\Parameters /v FileSizeLimitInBytes /t REG_DWORD /d 0xffffffff
net stop webclient
net start webclient
```

### macOS Finder Connection Drops

**Problem**: Network drive disconnects frequently

**Solutions**:
1. Use Mountain Duck instead of Finder
2. Reduce "Energy Saver" sleep timeout
3. Check firewall isn't blocking connections

---

## Technical Details

### WebDAV Methods Supported

- **PROPFIND**: List directory contents, get file properties
- **GET**: Download files
- **PUT**: Upload files
- **DELETE**: Delete files/folders
- **MKCOL**: Create folders
- **MOVE**: Rename/move files
- **COPY**: Copy files
- **LOCK/UNLOCK**: File locking for concurrent access

### File Metadata

WsgiDAV maintains metadata:
- Content-Type (MIME type)
- Content-Length (file size)
- Last-Modified timestamp
- ETag (for caching)
- Resource type (file vs collection)

### Locking

- Supports WebDAV locking for concurrent access
- Prevents simultaneous edits from multiple clients
- Locks expire automatically after timeout

### Storage Layout

```
/app/storage/
└── user_2/              # User storage (andy)
    ├── Documents/
    ├── Downloads/
    ├── Pictures/
    ├── Projects/
    └── ...
```

Each user's files are isolated in `/app/storage/user_{id}/`

---

## Comparison vs Nextcloud

Our WebDAV implementation provides similar functionality to Nextcloud's desktop sync:

| Feature | Files WebDAV | Nextcloud |
|---------|-------------|-----------|
| Two-way sync | ✅ | ✅ |
| Offline access | ✅ (with Mountain Duck) | ✅ |
| Smart sync | ✅ (with Mountain Duck) | ✅ |
| File versioning | ❌ (future) | ✅ |
| Sharing | ✅ (via web) | ✅ |
| Encryption | ✅ (HTTPS) | ✅ |
| SSO integration | ✅ Portal | ✅ SAML/LDAP |
| Mobile apps | ❌ (WebDAV generic) | ✅ Native apps |
| Desktop client | 3rd party | Native client |

**Our Advantages**:
- Simpler architecture (no separate sync protocol)
- Works with any WebDAV client
- Integrated with Portal SSO
- Lower resource usage

**Nextcloud Advantages**:
- Native desktop/mobile apps
- Built-in file versioning
- More advanced sharing options
- Activity tracking

---

## Client Recommendations

### Best Overall: Mountain Duck
- **Platforms**: macOS, Windows
- **Price**: $39 (free trial)
- **Pros**: Smart sync, offline mode, best performance
- **Cons**: Not free

### Best Free (Windows): RaiDrive
- **Platform**: Windows only
- **Price**: Free
- **Pros**: Easy setup, good performance
- **Cons**: No smart sync, Windows only

### Best Free (macOS): Mountain Duck Trial → Finder
- **Platform**: macOS
- **Price**: Free
- **Pros**: Built-in, no installation
- **Cons**: Poor performance, no smart sync

### Best Free (Linux): davfs2
- **Platform**: Linux
- **Price**: Free
- **Pros**: Auto-mount, command line access
- **Cons**: Manual setup, basic features

---

## Future Enhancements

Potential improvements:

1. **File Versioning**: Keep previous versions of files
2. **Conflict Resolution**: Better handling of simultaneous edits
3. **Selective Sync**: Choose which folders to sync
4. **Bandwidth Throttling**: Limit sync speed
5. **Native Mobile Apps**: iOS/Android apps
6. **Activity Log**: Track file changes and access
7. **Encryption**: Client-side encryption for sensitive files
8. **Quota Management**: Per-user storage limits

---

## Support

For issues or questions:

1. Check this documentation
2. Review logs: `docker logs files-app`
3. Test web interface: https://rm.swhgrp.com/files/
4. Contact system administrator

---

## Related Documentation

- [Files System Overview](files-system-overview.md)
- [Portal SSO Integration](portal-sso-integration.md)
- [Files vs Nextcloud Comparison](files-vs-nextcloud-comparison.md)

---

**Last Updated**: November 14, 2025
**Version**: 1.0.0
