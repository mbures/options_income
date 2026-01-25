#!/home/martin/.pyenv/shims/python
import ssl
import http.server

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(
    '/etc/letsencrypt/live/dirtydata.ai/fullchain.pem',
    '/etc/letsencrypt/live/dirtydata.ai/privkey.pem'
)

server = http.server.HTTPServer(('0.0.0.0', 8443), http.server.SimpleHTTPRequestHandler)
server.socket = context.wrap_socket(server.socket, server_side=True)

print("Test server running on https://dirtydata.ai:8443")
print("Press Ctrl+C to stop")
server.serve_forever()
