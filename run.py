"""
Startup script for WikiHop - Wikipedia Link Hop Counter.
Runs the FastAPI web server on https://localhost:8005.
"""

import datetime
import ipaddress
import os
import sys
import webbrowser
import uvicorn


def get_or_create_ssl_cert(cert_file: str = "cert.pem", key_file: str = "key.pem"):
    """
    Ensure an SSL certificate and private key exist for HTTPS server startup.
    Generates a self-signed certificate if not present.
    """
    if os.path.exists(cert_file) and os.path.exists(key_file):
        return cert_file, key_file

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "WikiHop Development"),
        ])

        now = datetime.datetime.now(datetime.timezone.utc)
        san = x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(san, critical=False)
            .sign(key, hashes.SHA256())
        )

        with open(key_file, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))

        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        return cert_file, key_file
    except Exception as e:
        print(f"Warning: Could not automatically generate SSL certificate: {e}")
        return None, None


def main():
    port = 8005
    host = "127.0.0.1"
    url = f"https://{host}:{port}"
    cert_file, key_file = get_or_create_ssl_cert()

    print("=" * 60)
    print("  WikiHop - Wikipedia Link Hop Counter (Playwright)")
    print(f"  Starting web server at {url}")
    print("=" * 60)

    # Launch browser automatically
    try:
        webbrowser.open(url)
    except Exception:
        pass

    ssl_kwargs = {}
    if cert_file and key_file and os.path.exists(cert_file) and os.path.exists(key_file):
        ssl_kwargs["ssl_certfile"] = cert_file
        ssl_kwargs["ssl_keyfile"] = key_file

    uvicorn.run("main:app", host=host, port=port, reload=False, ws="auto", **ssl_kwargs)


if __name__ == "__main__":
    main()
