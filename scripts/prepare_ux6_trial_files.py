"""Create passive QA documents/certificate only under the owned native profile."""
from pathlib import Path
import datetime
import json
import zipfile
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.codex-local/ux-6'
launch = json.loads((QA / 'native-built-launch.json').read_text(encoding='utf-8-sig'))
profile = Path(launch['data']).resolve()
assert launch['identifier'] == 'ai.smarti.ux6built' and profile.is_relative_to(QA)
target = profile / 'workspace'
target.mkdir(exist_ok=True)
(target / 'UX6-Open-With.ux6').write_text('Isolated UX6 fixture. Select Notepad with Open With.\nשלום English 123', encoding='utf-8')
(target / 'UX6-reading.txt').write_text('שלום, זה קובץ QA בלבד.\nEnglish text and C:/QA/path, 123.\n' * 80, encoding='utf-8')
stream = b'BT /F1 18 Tf 40 740 Td (UX6 isolated PDF) Tj ET'
objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
data = b'%PDF-1.4\n'
offsets = []
for n, value in enumerate(objects, 1):
    offsets.append(len(data))
    data += f'{n} 0 obj\n'.encode() + value + b'\nendobj\n'
xref = len(data)
data += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets)
data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
(target / 'UX6-reading.pdf').write_bytes(data)
with zipfile.ZipFile(target / 'UX6-reading.docx', 'w', zipfile.ZIP_DEFLATED) as document:
    document.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    document.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    document.writestr('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:bidi/></w:pPr><w:r><w:t>מסמך QA מבודד — שלום English 123</w:t></w:r></w:p><w:sectPr/></w:body></w:document>')
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'UX6 isolated test CA')])
now = datetime.datetime.now(datetime.timezone.utc)
certificate = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(key, hashes.SHA256())
(target / 'UX6-test-ca.crt').write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
# No private key is saved; this certificate is only an import validation fixture.
print('Passive trial files ready in owned workspace')
