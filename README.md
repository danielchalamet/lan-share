# lan-share
Stream your Mac screen, windows, system audio and local videos to iPhone, Android or any modern browser over your local network. No mobile app, no cloud, no account. Just run it, scan the QR code and start watching.


# LAN Share

**Stream your Mac screen, windows, audio and local videos to iPhone, Android or any browser over your local network.**

LAN Share is a lightweight macOS utility for one surprisingly simple problem: sometimes you just want to leave your Mac where it is and continue watching or monitoring something from your phone.

Apple provides plenty of ways to move content *to* a Mac, use an iPad as an external display, or mirror an iPhone elsewhere, but there is still no simple built-in way to stream an arbitrary Mac window or the entire Mac screen directly to Safari on an iPhone, let alone to an Android device.

LAN Share fills that gap.

Run one command on your Mac, scan the QR code from your phone, and open the stream in a browser.

No dedicated mobile app. No account. No cloud service. No files leaving your local network.

## Quick Start

Clone the repository:

```bash
git clone https://github.com/danielchalamet/lan-share.git
cd lan-share
```

Start LAN Share:

```bash
./run.sh
```

On the first launch, macOS may ask for **Screen Recording** permission. Allow it for the Terminal application you are using.

LAN Share will print a local address and a QR code directly in Terminal.

Scan the QR code with your iPhone or Android phone, or open the displayed address manually in a browser.

Your Mac and phone should be connected to the same local network.

LAN Share automatically creates and manages its Python virtual environment and installs missing dependencies when necessary.

To stop the server:

```bash
Ctrl+C
```

### Share a media folder

You can optionally specify an initial media directory:

```bash
./run.sh --media "$HOME/Movies"
```

Or choose another port:

```bash
./run.sh --port 8080
```

Both options can be combined:

```bash
./run.sh --media "$HOME/Movies" --port 8080
```

Once LAN Share is running, additional media files can also be selected through the local interface without restarting the server.

## What it can do

- Stream the **entire Mac display**
- Stream an **individual application window**
- Capture **system/application audio together with video**
- Play **local video files** directly from your Mac
- Add and remove media files without restarting the server
- Open everything from **Safari, Chrome, or another modern browser**
- Generate a **QR code directly in Terminal**
- Use a persistent `.local` address through Bonjour/mDNS
- Support multiple viewers on the same local network
- Keep access protected with a persistent local access key
- Work entirely inside your **LAN**, without uploading your screen or media to external servers
- Interface available in **5 languages**

## Why?

The original use case was extremely simple:

> A movie is playing on the MacBook. The Mac is charging across the room. You want to walk away with your phone and continue watching it.

Opening a local video file is easy enough.

But then the obvious next question appears:

**Why can't I just stream a Mac window the same way I would share it during a video call?**

Apple already has technologies such as AirPlay and screen mirroring, but the usual direction is toward a Mac, Apple TV, or another supported display.

There is no equally simple built-in button for:

**Mac → iPhone**

and certainly no universal:

**Mac → Android browser**

LAN Share exists because that direction is useful too.

It evolved from a tiny local file server into a browser-based Mac streaming utility capable of transmitting an individual window, an entire display, audio, and local media.

## No mobile app required

The receiving device does not need LAN Share installed.

Your iPhone, Android phone, tablet, another Mac, PC, or practically any device with a modern browser can act as the viewer.

The Mac does the work.

The basic workflow is:

1. Run `./run.sh` on the Mac.
2. Scan the QR code.
3. Open LAN Share on your phone.
4. Select a window, display, or media file.
5. Start watching.

That's it.

## Local by design

LAN Share was built primarily for trusted home and local networks.

There is:

- no account
- no cloud relay
- no analytics service
- no media upload
- no external streaming server
- no STUN/TURN dependency

Your Mac captures the content and sends it directly across your local network.

This also means LAN Share is primarily designed for devices connected to the same LAN/Wi-Fi network rather than internet-wide remote access.

## Media sharing

LAN Share can also act as a lightweight local media browser.

You can select files from your Mac and make them available to connected devices without copying them to the phone first.

HTTP Range support allows compatible video files to seek normally, so you can jump forward and backward instead of waiting for the entire file to download.

Selected files are exposed through random internal IDs rather than revealing their real filesystem paths to the viewer.

## Screen and window streaming

Screen sharing is handled through Apple's native ScreenCaptureKit APIs.

You can choose between:

- an entire display
- an individual macOS window

Video is streamed over WebRTC using H.264, while audio is transmitted as Opus.

When sharing an individual window, LAN Share captures the audio associated with its application.

When sharing the whole screen, it can transmit system audio.

The microphone is intentionally not part of the stream.

This makes LAN Share closer to a small, private browser-based screen broadcast than a conventional remote-desktop application.

## Designed for the small things

LAN Share is useful when you want to:

- continue a movie from your Mac on your phone
- lie in bed while the Mac stays plugged in somewhere else
- monitor a render, export, upload, or long-running process from another room
- watch a Mac-only application from an iPhone or Android device
- show a window to several devices on the same Wi-Fi
- quickly share a local video without uploading it to Telegram, cloud storage, or another service
- turn an old phone or tablet into a temporary secondary viewing screen

LAN Share deliberately avoids becoming a full remote-desktop suite.

Its purpose is simple:

**get pixels, sound, and media from your Mac to a nearby browser with as little friction as possible.**

## Technology

LAN Share is intentionally lightweight and does not require building or installing a conventional `.app`.

Under the hood it uses:

- **ScreenCaptureKit** for display and window capture
- **CoreAudio** for audio capture
- **PyObjC** for native macOS APIs
- **WebRTC / aiortc** for real-time streaming
- **H.264** for video
- **Opus** for audio
- **aiohttp** for the local web server
- **Bonjour / mDNS** for a persistent `.local` address
- **HTTP Range** for seekable local media playback

The project runs directly from Terminal.

## Requirements

- macOS
- Python
- iPhone, Android phone, tablet, laptop, or another device with a modern browser
- both devices connected to the same local network
- Screen Recording permission on the Mac

No companion mobile application is required.

## Notes

LAN Share currently operates inside the local network and does not use STUN/TURN servers.

Some browsers, codecs, DRM-protected content, or macOS applications may impose their own capture or playback restrictions.

This project is still evolving, so bug reports, testing on different Macs and mobile devices, and contributions are welcome.

---

LAN Share started with a very mundane thought:

**“Why can't I simply open my MacBook screen on my phone?”**

Apparently, the answer was to build it.
