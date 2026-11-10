from flask import Flask, request
from ldap3 import Server, Connection, Tls, ALL
import ssl

app = Flask(__name__)

LDAP_HOST = "dc01.lab.local"
LDAP_PORT = 636
CA_FILE   = "/etc/ssl/certs/lab-root-ca.pem"

tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=CA_FILE)

PAGE = """
<form method="post">
  User: <input name="u"><br>
  Pass: <input name="p" type="password"><br>
  <input type="submit" value="Login">
</form>
<p>Result: {r}</p>
"""

def try_login(user, password):
    try:
        srv = Server(LDAP_HOST, port=LDAP_PORT, use_ssl=True, tls=tls, get_info=ALL)
        conn = Connection(srv, user=f"{user}@lab.local", password=password, auto_bind=True)
        conn.unbind()
        return "OK"
    except Exception as e:
        return f"FAIL ({type(e).__name__})"

@app.route("/", methods=["GET", "POST"])
def index():
    r = ""
    if request.method == "POST":
        r = try_login(request.form.get("u", ""), request.form.get("p", ""))
    return PAGE.format(r=r)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
