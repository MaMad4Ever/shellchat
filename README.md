# ShellChat
```
 ____   _   _  _____  _      _       ____  _   _     _     _____
/ ___| | | | || ____|| |    | |     / ___|| | | |   / \   |_   _|
\___ \ | |_| ||  _|  | |    | |    | |    | |_| |  / _ \    | |
 ___) ||  _  || |___ | |___ | |___ | |___ |  _  | / ___ \   | |
|____/ |_| |_||_____||_____||_____| \____||_| |_|/_/   \_\  |_|
```

A terminal-based chat application built with Python and Redis Pub/Sub. Users can communicate with each other in real time through shared chat rooms, directly from their terminals.

## ✨ Features

- **Real-time messaging** using Redis Pub/Sub.
- **Multiple chat rooms** with isolated channels.
- **Multiple color themes** with runtime switching.
- **Automatic reconnection** with exponential backoff.
- **Configurable Redis connection** with optional TLS and password authentication.
- **No message history** — messages are not stored.

## 🛠️ Requirements

- Python 3.10+
- A reachable Redis Server (see below)
- Python packages:
  - `redis`
  - `colorama`

## 📦 Installation

Clone the repository:

```bash
git clone https://github.com/MaMad4Ever/shellchat.git
cd shellchat
```

Install the required packages:

```bash
pip install redis colorama
```

Make sure a Redis server is running and accessible.

## 🚀 Usage

Start the application using a local Redis server:

```bash
python3 main.py --host 127.0.0.1
```

Connect to a remote Redis server:

```bash
python3 main.py --host 192.168.1.100 --port 6379
```

Connect with authentication:

```bash
python3 main.py --host 192.168.1.100 --password YOUR_PASSWORD
```

Connect using TLS:

```bash
python3 main.py --host redis.example.com --port 6379 --tls
```

### Command-line Arguments

| Argument | Description | Default |
|---|---|---|
| `--host` | Redis server address (required) | — |
| `--port` | Redis server port | `6379` |
| `--password` | Redis authentication password | `None` |
| `--tls` | Enable TLS connection | Disabled |
| `--room` | Chat room name | `general` |
| `--name` | Your nickname | Random name |
| `--theme` | Initial color theme | `matrix` |

## 💬 Chat Commands

| Command | Description |
|---|---|
| `/nick NAME` | Change your nickname |
| `/theme` | Display available themes |
| `/theme NAME` | Change the current color theme |
| `/clear` | Clear the terminal screen |
| `/quit` | Exit the chat |

## 🎨 Available Themes

The application includes five built-in color themes:

- `matrix`
- `cyber`
- `blood`
- `ice`
- `mono`

You can select a theme when launching the application:

```bash
python3 main.py --host 192.168.1.100 --theme cyber
```

Or change it while chatting:

```text
/theme blood
```
