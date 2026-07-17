#!/usr/bin/env python3
import socket, threading
from socks import socksocket, SOCKS5

LISTEN = "0.0.0.0"
PORT = 9091
SOCKS5_HOST = "127.0.0.1"
SOCKS5_PORT = 9090  # local ssh -D inside same container

def handle(client):
    try:
        data = client.recv(4096)
        if not data:
            client.close(); return
        lines = data.split(b"\r\n")
        method, target, _ = lines[0].decode().split(" ")
        host, port = target.rsplit(":", 1)
        port = int(port)
        # Connect via SOCKS5
        s = socksocket()
        s.set_proxy(SOCKS5, SOCKS5_HOST, SOCKS5_PORT)
        s.settimeout(30)
        s.connect((host, port))
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

        def pipe(a, b):
            try:
                while True:
                    buf = a.recv(65536)
                    if not buf:
                        break
                    b.sendall(buf)
            except Exception:
                pass
            finally:
                for sock in (a, b):
                    try: sock.close()
                    except: pass

        threading.Thread(target=pipe, args=(client, s), daemon=True).start()
        threading.Thread(target=pipe, args=(s, client), daemon=True).start()
    except Exception as e:
        try:
            client.sendall(f"HTTP/1.1 502 Bad Gateway\r\n\r\n{str(e)}".encode())
        except Exception:
            pass
        try: client.close()
        except: pass

def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN, PORT))
    srv.listen(128)
    print(f"[proxy] listening on {LISTEN}:{PORT} -> socks5 {SOCKS5_HOST}:{SOCKS5_PORT}", flush=True)
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()

if __name__ == "__main__":
    main()
