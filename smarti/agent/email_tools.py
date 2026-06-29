"""Email provider configuration, IMAP/SMTP helpers, search, send, folders, and attachments."""
from .shared import *


class EmailToolsMixin:
    def _email_provider(self, address=None):
        address = str(address or self._ensure_secret_loaded("email_address") or "").lower()
        domain = address.rsplit("@", 1)[-1] if "@" in address else ""
        if domain in {"gmail.com", "googlemail.com"}:
            return "gmail"
        if domain in {"outlook.com", "hotmail.com", "live.com", "msn.com"}:
            return "outlook"
        if domain in {"yahoo.com", "ymail.com", "rocketmail.com"}:
            return "yahoo"
        return "custom"

    def _email_config(self):
        user = self._ensure_secret_loaded("email_address")
        pwd = self._ensure_secret_loaded("email_password")
        provider = self._email_provider(user)
        defaults = {
            "gmail": {
                "imap_host": "imap.gmail.com", "imap_port": 993,
                "smtp_host": "smtp.gmail.com", "smtp_port": 587,
                "drafts": "[Gmail]/Drafts", "sent": "[Gmail]/Sent Mail",
                "archive": "[Gmail]/All Mail", "trash": "[Gmail]/Trash",
            },
            "outlook": {
                "imap_host": "outlook.office365.com", "imap_port": 993,
                "smtp_host": "smtp.office365.com", "smtp_port": 587,
                "drafts": "Drafts", "sent": "Sent Items",
                "archive": "Archive", "trash": "Deleted Items",
            },
            "yahoo": {
                "imap_host": "imap.mail.yahoo.com", "imap_port": 993,
                "smtp_host": "smtp.mail.yahoo.com", "smtp_port": 587,
                "drafts": "Draft", "sent": "Sent",
                "archive": "Archive", "trash": "Trash",
            },
            "custom": {
                "imap_host": "imap.gmail.com", "imap_port": 993,
                "smtp_host": "smtp.gmail.com", "smtp_port": 587,
                "drafts": "Drafts", "sent": "Sent",
                "archive": "Archive", "trash": "Trash",
            },
        }[provider]

        def as_int(value, fallback):
            try:
                return int(value)
            except Exception:
                return fallback

        return {
            "user": user,
            "password": pwd,
            "provider": provider,
            "from_name": str(self.settings.get("email_from_name", "") or "").strip(),
            "imap_host": str(self.settings.get("email_imap_host") or defaults["imap_host"]),
            "imap_port": as_int(self.settings.get("email_imap_port"), defaults["imap_port"]),
            "imap_ssl": bool(self.settings.get("email_imap_ssl", True)),
            "smtp_host": str(self.settings.get("email_smtp_host") or defaults["smtp_host"]),
            "smtp_port": as_int(self.settings.get("email_smtp_port"), defaults["smtp_port"]),
            "smtp_ssl": bool(self.settings.get("email_smtp_ssl", False)),
            "smtp_starttls": bool(self.settings.get("email_smtp_starttls", True)),
            "drafts": str(self.settings.get("email_drafts_mailbox") or defaults["drafts"]),
            "sent": str(self.settings.get("email_sent_mailbox") or defaults["sent"]),
            "archive": str(self.settings.get("email_archive_mailbox") or defaults["archive"]),
            "trash": str(self.settings.get("email_trash_mailbox") or defaults["trash"]),
            "max_attachment_mb": as_int(self.settings.get("email_max_attachment_mb"), 20),
        }

    def _email_require_credentials(self):
        cfg = self._email_config()
        if not cfg["user"] or not cfg["password"]:
            raise ValueError("Credentials missing. Set email address and app password in Smarti settings.")
        return cfg

    def _email_ssl_context(self):
        if self._allow_insecure_ssl():
            return ssl._create_unverified_context()
        return None

    def _email_mailbox_arg(self, mailbox):
        mailbox = str(mailbox or "INBOX").strip() or "INBOX"
        if mailbox.upper() == "INBOX":
            return "INBOX"
        return '"' + mailbox.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _email_connect_imap(self):
        cfg = self._email_require_credentials()
        self._raise_if_cancelled()
        context = self._email_ssl_context()
        if cfg["imap_ssl"]:
            if context:
                mail = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"], timeout=30, ssl_context=context)
            else:
                mail = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"], timeout=30)
        else:
            mail = imaplib.IMAP4(cfg["imap_host"], cfg["imap_port"], timeout=30)
        mail.login(cfg["user"], cfg["password"])
        return mail

    def _email_select_mailbox(self, mail, mailbox="INBOX", readonly=True):
        status, data = mail.select(self._email_mailbox_arg(mailbox), readonly=readonly)
        if status != "OK":
            raise RuntimeError(f"Could not select mailbox '{mailbox}': {data}")
        return data

    def _email_decode_header(self, value):
        parts = decode_header(str(value or ""))
        decoded = []
        for part, enc in parts:
            if isinstance(part, bytes):
                for candidate in [enc, "utf-8", "windows-1255", "iso-8859-8", "latin-1"]:
                    if not candidate:
                        continue
                    try:
                        decoded.append(part.decode(candidate, "replace"))
                        break
                    except Exception:
                        continue
                else:
                    decoded.append(part.decode("utf-8", "replace"))
            elif part is not None:
                decoded.append(str(part))
        return "".join(decoded)

    def _email_html_to_text(self, value):
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", str(value or ""))
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</p\s*>", "\n", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = html.unescape(text)
        return re.sub(r"[ \t\r\f\v]+", " ", text).replace(" \n", "\n").strip()

    def _email_normalize_search_text(self, value):
        text = unicodedata.normalize("NFKD", str(value or "")).lower()
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[\u0591-\u05c7]", "", text)
        text = re.sub(r"[\"'`״׳.,;:!?()\[\]{}<>|/\\_-]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _email_text_matches(self, haystack, needle):
        needle_norm = self._email_normalize_search_text(needle)
        if not needle_norm:
            return True
        hay_norm = self._email_normalize_search_text(haystack)
        if needle_norm in hay_norm:
            return True
        needle_compact = re.sub(r"\s+", "", needle_norm)
        hay_compact = re.sub(r"\s+", "", hay_norm)
        if needle_compact and needle_compact in hay_compact:
            return True
        tokens = [tok for tok in needle_norm.split() if tok]
        return bool(tokens) and all(tok in hay_norm or tok in hay_compact for tok in tokens)

    def _email_message_body(self, msg, max_chars=4000, max_body_chars=None):
        if max_body_chars is not None:
            max_chars = max_body_chars
        max_chars = max(0, int(max_chars or 4000))
        candidates = []
        try:
            body_part = msg.get_body(preferencelist=("plain", "html"))
            if body_part:
                content = body_part.get_content()
                if body_part.get_content_subtype() == "html":
                    content = self._email_html_to_text(content)
                candidates.append(content)
        except Exception:
            pass
        if not candidates:
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    disp = str(part.get_content_disposition() or "").lower()
                    if disp == "attachment" or ctype not in {"text/plain", "text/html"}:
                        continue
                    try:
                        raw = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        text = raw.decode(charset, "replace") if raw else str(part.get_payload())
                        candidates.append(self._email_html_to_text(text) if ctype == "text/html" else text)
                        if ctype == "text/plain":
                            break
                    except Exception:
                        continue
            else:
                try:
                    raw = msg.get_payload(decode=True)
                    charset = msg.get_content_charset() or "utf-8"
                    text = raw.decode(charset, "replace") if raw else str(msg.get_payload())
                    candidates.append(self._email_html_to_text(text) if msg.get_content_type() == "text/html" else text)
                except Exception:
                    pass
        text = "\n".join(t for t in candidates if t).strip()
        return text[:max_chars] + ("..." if max_chars and len(text) > max_chars else "")

    def _email_attachment_metadata(self, msg):
        attachments = []
        for part in msg.iter_attachments():
            filename = self._email_decode_header(part.get_filename() or "")
            try:
                payload = part.get_payload(decode=True) or b""
                size = len(payload)
            except Exception:
                size = None
            attachments.append({
                "filename": filename or "attachment",
                "content_type": part.get_content_type(),
                "size": size,
                "content_id": str(part.get("Content-ID", "") or "").strip("<>"),
            })
        return attachments

    def _email_fetch_message(self, mail, uid):
        uid = str(uid).strip()
        if not uid:
            raise ValueError("Missing message UID.")
        self._raise_if_cancelled()
        status, data = mail.uid("FETCH", uid, "(BODY.PEEK[] FLAGS INTERNALDATE RFC822.SIZE)")
        if status != "OK":
            raise RuntimeError(f"Fetch failed for UID {uid}.")
        raw = None
        meta = b""
        for item in data:
            if isinstance(item, tuple):
                meta += item[0] if isinstance(item[0], bytes) else str(item[0]).encode("utf-8", "replace")
                raw = item[1]
            elif isinstance(item, bytes):
                meta += b" " + item
        if raw is None:
            raise RuntimeError(f"No message data returned for UID {uid}.")
        msg = BytesParser(policy=email_policy.default).parsebytes(raw)
        flags_match = re.search(rb"FLAGS \((.*?)\)", meta)
        size_match = re.search(rb"RFC822\.SIZE (\d+)", meta)
        date_match = re.search(rb'INTERNALDATE "([^"]+)"', meta)
        return msg, {
            "uid": uid,
            "flags": (flags_match.group(1).decode("utf-8", "replace").split() if flags_match else []),
            "size": int(size_match.group(1)) if size_match else len(raw),
            "internal_date": date_match.group(1).decode("utf-8", "replace") if date_match else "",
        }

    def _email_fetch_message_header(self, mail, uid):
        uid = str(uid).strip()
        if not uid:
            raise ValueError("Missing message UID.")
        self._raise_if_cancelled()
        status, data = mail.uid("FETCH", uid, "(BODY.PEEK[HEADER] FLAGS INTERNALDATE RFC822.SIZE)")
        if status != "OK":
            raise RuntimeError(f"Header fetch failed for UID {uid}.")
        raw = None
        meta = b""
        for item in data:
            if isinstance(item, tuple):
                meta += item[0] if isinstance(item[0], bytes) else str(item[0]).encode("utf-8", "replace")
                raw = item[1]
            elif isinstance(item, bytes):
                meta += b" " + item
        if raw is None:
            raise RuntimeError(f"No header data returned for UID {uid}.")
        msg = BytesParser(policy=email_policy.default).parsebytes(raw)
        flags_match = re.search(rb"FLAGS \((.*?)\)", meta)
        size_match = re.search(rb"RFC822\.SIZE (\d+)", meta)
        date_match = re.search(rb'INTERNALDATE "([^"]+)"', meta)
        return msg, {
            "uid": uid,
            "flags": (flags_match.group(1).decode("utf-8", "replace").split() if flags_match else []),
            "size": int(size_match.group(1)) if size_match else None,
            "internal_date": date_match.group(1).decode("utf-8", "replace") if date_match else "",
        }

    def _email_record_from_message(self, uid, msg, meta=None, include_body=False, include_headers=False, include_attachments=True, max_body_chars=2000):
        meta = meta or {"uid": str(uid)}
        date_value = self._email_decode_header(msg.get("Date", ""))
        try:
            date_iso = parsedate_to_datetime(str(msg.get("Date", ""))).isoformat()
        except Exception:
            date_iso = ""
        record = {
            "uid": str(uid),
            "subject": self._email_decode_header(msg.get("Subject", "")),
            "from": self._email_decode_header(msg.get("From", "")),
            "to": self._email_decode_header(msg.get("To", "")),
            "cc": self._email_decode_header(msg.get("Cc", "")),
            "date": date_value,
            "date_iso": date_iso,
            "message_id": str(msg.get("Message-ID", "") or "").strip(),
            "flags": meta.get("flags", []),
            "size": meta.get("size"),
        }
        if include_body:
            record["body"] = self._email_message_body(msg, max_body_chars=max_body_chars)
        if include_attachments:
            record["attachments"] = self._email_attachment_metadata(msg)
        if include_headers:
            record["headers"] = {
                name: self._email_decode_header(msg.get(name, ""))
                for name in ["Reply-To", "References", "In-Reply-To", "List-Unsubscribe", "Delivered-To"]
                if msg.get(name)
            }
        return record

    def _email_quote_search_text(self, value):
        value = str(value or "").replace("\\", "\\\\").replace('"', '\\"')
        return f'"{value}"'

    def _email_imap_date(self, value):
        raw = str(value or "").strip()
        for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(raw[:10 if fmt == "%Y-%m-%d" else len(raw)], fmt)
                return dt.strftime("%d-%b-%Y")
            except Exception:
                continue
        return ""

    def _email_iso_date_from_any(self, value):
        raw = str(value or "").strip()
        for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(raw[:10 if fmt == "%Y-%m-%d" else len(raw)], fmt).strftime("%Y-%m-%d")
            except Exception:
                continue
        return ""

    def _email_parse_loose_query(self, args):
        parsed = copy.deepcopy(args or {})
        query = str(parsed.get("query", "") or "")
        if not query:
            return parsed
        patterns = {
            "from": r'(?i)\bfrom\s*:\s*"([^"]+)"|\bfrom\s+"([^"]+)"',
            "to_filter": r'(?i)\bto\s*:\s*"([^"]+)"|\bto\s+"([^"]+)"',
            "subject_filter": r'(?i)\bsubject\s*:\s*"([^"]+)"|\bsubject\s+"([^"]+)"',
        }
        for key, pattern in patterns.items():
            if parsed.get(key):
                continue
            match = re.search(pattern, query)
            if match:
                parsed[key] = next((g for g in match.groups() if g), "")
        if not parsed.get("since"):
            match = re.search(r"(?i)\bsince\s+([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", query)
            if match:
                parsed["since"] = self._email_iso_date_from_any(match.group(1)) or match.group(1)
        if not parsed.get("before"):
            match = re.search(r"(?i)\bbefore\s+([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", query)
            if match:
                parsed["before"] = self._email_iso_date_from_any(match.group(1)) or match.group(1)
        if re.search(r'(?i)\b(from|to|subject|since|before)\b', query):
            cleaned = re.sub(r'(?i)\b(from|to|subject)\s*:?\s*"[^"]+"', " ", query)
            cleaned = re.sub(r"(?i)\b(since|before)\s+([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", " ", cleaned)
            parsed["query"] = re.sub(r"\s+", " ", cleaned).strip()
        return parsed

    def _email_uid_search(self, mail, criteria, charset=None, literal=None):
        criteria = [c for c in criteria if c not in (None, "")]
        if not criteria:
            criteria = ["ALL"]
        if literal is not None:
            mail.literal = str(literal).encode("utf-8")
        args = []
        if charset:
            args.extend(["CHARSET", charset])
        args.extend(criteria)
        status, data = mail.uid("SEARCH", *args)
        if status != "OK":
            raise RuntimeError(f"Search failed: {data}")
        raw = data[0] if data else b""
        if isinstance(raw, str):
            raw = raw.encode("ascii", "ignore")
        return [u.decode("ascii", "ignore") for u in raw.split() if u]

    def _email_search_uids(self, mail, args):
        cfg = self._email_config()
        search_mode = str(args.get("search_mode") or "auto").strip().lower()
        query = str(args.get("query", "") or "").strip()
        criteria = []
        literal = None
        charset = None
        gmail_raw_parts = []

        if args.get("unread"):
            criteria.append("UNSEEN")
            gmail_raw_parts.append("is:unread")
        if args.get("flagged"):
            criteria.append("FLAGGED")
            gmail_raw_parts.append("is:starred")
        if args.get("has_attachment"):
            gmail_raw_parts.append("has:attachment")
        if args.get("since"):
            imap_date = self._email_imap_date(args.get("since"))
            if imap_date:
                criteria.extend(["SINCE", imap_date])
                gmail_raw_parts.append("after:" + str(args.get("since")).replace("-", "/"))
        if args.get("before"):
            imap_date = self._email_imap_date(args.get("before"))
            if imap_date:
                criteria.extend(["BEFORE", imap_date])
                gmail_raw_parts.append("before:" + str(args.get("before")).replace("-", "/"))

        sender = str(args.get("from", "") or "").strip()
        to_filter = str(args.get("to_filter", "") or "").strip()
        subject_filter = str(args.get("subject_filter", "") or "").strip()
        for key, value, imap_key in [("from", sender, "FROM"), ("to", to_filter, "TO"), ("subject", subject_filter, "SUBJECT")]:
            if value:
                gmail_raw_parts.append(f'{key}:({value})')
                if value.isascii():
                    criteria.extend([imap_key, self._email_quote_search_text(value)])

        if cfg["provider"] == "gmail" and search_mode in {"auto", "gmail"} and (query or gmail_raw_parts):
            raw_query = " ".join([query] + gmail_raw_parts).strip()
            return self._email_uid_search(mail, ["X-GM-RAW"], charset="UTF-8", literal=raw_query)

        if query:
            if query.isascii():
                criteria.extend(["TEXT", self._email_quote_search_text(query)])
            else:
                criteria.append("TEXT")
                charset = "UTF-8"
                literal = query
            if args.get("has_attachment") and cfg["provider"] != "gmail":
                # Generic IMAP has no portable attachment search; filter after fetching metadata.
                pass
        return self._email_uid_search(mail, criteria or ["ALL"], charset=charset, literal=literal)

    def _email_message_date_for_filter(self, msg):
        try:
            return parsedate_to_datetime(str(msg.get("Date", ""))).replace(tzinfo=None)
        except Exception:
            return None

    def _email_matches_local_filters(self, msg, args, body_text=""):
        query = str(args.get("query", "") or "").strip()
        sender = self._email_decode_header(msg.get("From", ""))
        recipient = " ".join([
            self._email_decode_header(msg.get("To", "")),
            self._email_decode_header(msg.get("Cc", "")),
            self._email_decode_header(msg.get("Bcc", "")),
        ])
        subject = self._email_decode_header(msg.get("Subject", ""))
        header_text = "\n".join([sender, recipient, subject, self._email_decode_header(msg.get("Reply-To", ""))])
        if args.get("from") and not self._email_text_matches(sender, args.get("from")):
            return False
        if args.get("to_filter") and not self._email_text_matches(recipient, args.get("to_filter")):
            return False
        if args.get("subject_filter") and not self._email_text_matches(subject, args.get("subject_filter")):
            return False
        if query and not self._email_text_matches(header_text + "\n" + body_text, query):
            return False
        msg_date = self._email_message_date_for_filter(msg)
        if msg_date and args.get("since"):
            since = self._email_iso_date_from_any(args.get("since"))
            if since and msg_date < datetime.strptime(since, "%Y-%m-%d"):
                return False
        if msg_date and args.get("before"):
            before = self._email_iso_date_from_any(args.get("before"))
            if before and msg_date >= datetime.strptime(before, "%Y-%m-%d"):
                return False
        if args.get("has_attachment") and not self._email_attachment_metadata(msg):
            return False
        return True

    def _email_scan_uids(self, mail, base_uids, args):
        scan_bodies = bool(args.get("scan_bodies", False))
        try:
            scan_limit = max(0, int(args.get("scan_limit") or 0))
        except Exception:
            scan_limit = 0
        matches = []
        scanned = 0
        for uid in base_uids:
            self._raise_if_cancelled()
            if scan_limit and scanned >= scan_limit:
                break
            scanned += 1
            try:
                if scan_bodies or args.get("has_attachment"):
                    msg, _ = self._email_fetch_message(mail, uid)
                    body_text = self._email_message_body(msg, max_chars=int(args.get("max_body_chars") or 4000))
                else:
                    msg, _ = self._email_fetch_message_header(mail, uid)
                    body_text = ""
                if self._email_matches_local_filters(msg, args, body_text=body_text):
                    matches.append(uid)
            except Exception as e:
                logging.warning(f"Email local scan skipped UID {uid}: {e}")
                continue
        return matches, scanned

    def _email_list_folders(self):
        mail = self._email_connect_imap()
        try:
            status, data = mail.list()
            if status != "OK":
                raise RuntimeError(f"Folder list failed: {data}")
            folders = []
            for raw in data or []:
                text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
                match = re.match(r'\((?P<attrs>.*?)\)\s+"(?P<delimiter>.*?)"\s+(?P<name>.*)$', text)
                if match:
                    name = match.group("name").strip()
                    if name.startswith('"') and name.endswith('"'):
                        name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
                    folders.append({
                        "name": name,
                        "attributes": match.group("attrs").split(),
                        "delimiter": match.group("delimiter"),
                    })
                else:
                    folders.append({"name": text, "attributes": [], "delimiter": "/"})
            return {"status": "ok", "folders": folders}
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def _email_list_folders_on_connection(self, mail):
        status, data = mail.list()
        if status != "OK":
            raise RuntimeError(f"Folder list failed: {data}")
        folders = []
        for raw in data or []:
            text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            match = re.match(r'\((?P<attrs>.*?)\)\s+"(?P<delimiter>.*?)"\s+(?P<name>.*)$', text)
            if not match:
                continue
            attrs = match.group("attrs").split()
            if any(attr.upper() == "\\NOSELECT" for attr in attrs):
                continue
            name = match.group("name").strip()
            if name.startswith('"') and name.endswith('"'):
                name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            folders.append(name)
        return folders

    def _email_recipients(self, value):
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            raw_items = [str(v) for v in value if str(v).strip()]
        else:
            raw_items = [str(value)]
        result = []
        for name, addr in getaddresses(raw_items):
            addr = addr.strip()
            if "@" in addr:
                result.append(formataddr((name, addr)) if name else addr)
        return result

    def _email_css_value(self, value, default=""):
        text = str(value or "").strip()
        if not text or any(ch in text for ch in "<>{}\r\n"):
            return default
        return text

    def _email_wants_html(self, args):
        mode = str(args.get("content_mode") or "auto").strip().lower()
        if mode in {"html", "both"}:
            return True
        if mode == "plain":
            return False
        style_keys = ("direction", "text_align", "font_family", "font_size_px", "line_height", "text_color", "background_color", "custom_css")
        return bool(args.get("html_body") or any(str(args.get(key) or "").strip() for key in style_keys))

    def _email_html_document(self, args, body, html_body):
        html_body = str(html_body or "")
        if html_body and re.search(r"<\s*(?:!doctype|html|body)\b", html_body, flags=re.IGNORECASE):
            return html_body
        source_text = html_body or html.escape(str(body or " ")).replace("\n", "<br>\n")
        direction = str(args.get("direction") or "auto").strip().lower()
        if direction not in {"rtl", "ltr"}:
            combined = html.unescape(re.sub(r"<[^>]+>", " ", source_text))
            direction = "rtl" if re.search(r"[\u0590-\u05ff]", combined) else "ltr"
        align = str(args.get("text_align") or "auto").strip().lower()
        if align not in {"right", "left", "center", "justify"}:
            align = "right" if direction == "rtl" else "left"
        try:
            font_size = int(args.get("font_size_px") or 16)
        except Exception:
            font_size = 16
        font_size = max(10, min(36, font_size))
        font_family = self._email_css_value(args.get("font_family"), "Arial, 'Segoe UI', sans-serif")
        line_height = self._email_css_value(args.get("line_height"), "1.6")
        text_color = self._email_css_value(args.get("text_color"), "#111111")
        background_color = self._email_css_value(args.get("background_color"), "#ffffff")
        custom_css = str(args.get("custom_css") or "").strip()
        body_style = (
            f"direction:{direction}; text-align:{align}; font-family:{font_family}; "
            f"font-size:{font_size}px; line-height:{line_height}; color:{text_color}; "
            f"background:{background_color}; margin:0; padding:24px;"
        )
        return (
            "<!doctype html>\n"
            f"<html lang=\"he\" dir=\"{direction}\">\n"
            "<head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<style>body {{{body_style}}} .smarti-email-body {{max-width: 760px; margin: 0 auto;}} {custom_css}</style>\n"
            "</head>\n"
            f"<body dir=\"{direction}\"><div class=\"smarti-email-body\" dir=\"{direction}\">{source_text}</div></body>\n"
            "</html>"
        )

    def _email_apply_outbound_headers(self, msg, args, from_addr):
        reply_to_list = self._email_recipients(args.get("reply_to"))
        if reply_to_list:
            msg["Reply-To"] = ", ".join(reply_to_list)
        priority = str(args.get("priority") or "normal").strip().lower()
        if priority == "high":
            msg["Importance"] = "high"
            msg["Priority"] = "urgent"
            msg["X-Priority"] = "1"
        elif priority == "low":
            msg["Importance"] = "low"
            msg["Priority"] = "non-urgent"
            msg["X-Priority"] = "5"
        if bool(args.get("request_read_receipt")):
            msg["Disposition-Notification-To"] = ", ".join(reply_to_list) if reply_to_list else from_addr
        headers = args.get("headers") or {}
        if isinstance(headers, dict):
            protected = {
                "from", "to", "cc", "bcc", "subject", "date", "message-id", "mime-version",
                "content-type", "content-transfer-encoding", "reply-to", "importance",
                "priority", "x-priority", "disposition-notification-to",
            }
            for name, value in headers.items():
                header_name = str(name or "").strip()
                if not header_name or header_name.lower() in protected:
                    continue
                if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+\-.^_`|~]+", header_name):
                    continue
                if isinstance(value, (list, tuple)):
                    value = ", ".join(str(item) for item in value)
                header_value = str(value or "").replace("\r", " ").replace("\n", " ").strip()
                if header_value:
                    msg[header_name] = header_value

    def _email_build_outbound_message(self, args, original=None, mode="send"):
        cfg = self._email_require_credentials()
        msg = EmailMessage()
        from_name = str(args.get("from_name") or cfg["from_name"] or "").strip()
        from_addr = formataddr((from_name, cfg["user"])) if from_name else cfg["user"]
        msg["From"] = from_addr
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=cfg["user"].split("@")[-1] if "@" in cfg["user"] else None)

        to_list = self._email_recipients(args.get("to"))
        cc_list = self._email_recipients(args.get("cc"))
        bcc_list = self._email_recipients(args.get("bcc"))
        if mode == "reply" and original and not to_list:
            reply_to = original.get("Reply-To") or original.get("From")
            to_list = self._email_recipients(reply_to)
        if not to_list and mode != "draft":
            raise ValueError("Missing recipient.")
        if to_list:
            msg["To"] = ", ".join(to_list)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        self._email_apply_outbound_headers(msg, args, from_addr)

        subject = str(args.get("subject", "") or "").strip()
        if original is not None and not subject:
            original_subject = self._email_decode_header(original.get("Subject", ""))
            if mode == "reply":
                subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
            elif mode == "forward":
                subject = original_subject if original_subject.lower().startswith("fwd:") else f"Fwd: {original_subject}"
        msg["Subject"] = subject

        body = str(args.get("body", "") or "")
        html_body = str(args.get("html_body", "") or "")
        if original is not None and mode in {"reply", "forward"}:
            original_text = self._email_message_body(original, max_body_chars=6000)
            if mode == "reply":
                quoted = "\n".join("> " + line for line in original_text.splitlines())
                body = body.rstrip() + f"\n\nOn {self._email_decode_header(original.get('Date', ''))}, {self._email_decode_header(original.get('From', ''))} wrote:\n{quoted}"
                original_id = str(original.get("Message-ID", "") or "").strip()
                if original_id:
                    msg["In-Reply-To"] = original_id
                    refs = str(original.get("References", "") or "").strip()
                    msg["References"] = (refs + " " + original_id).strip()
            else:
                body = body.rstrip() + "\n\n---------- Forwarded message ----------\n"
                body += f"From: {self._email_decode_header(original.get('From', ''))}\n"
                body += f"Date: {self._email_decode_header(original.get('Date', ''))}\n"
                body += f"Subject: {self._email_decode_header(original.get('Subject', ''))}\n"
                body += f"To: {self._email_decode_header(original.get('To', ''))}\n\n{original_text}"

        if self._email_wants_html(args):
            html_document = self._email_html_document(args, body, html_body)
            msg.set_content(body or self._email_html_to_text(html_document) or " ", charset="utf-8")
            msg.add_alternative(html_document, subtype="html", charset="utf-8")
        else:
            msg.set_content(body or " ", charset="utf-8")

        max_bytes = max(1, cfg["max_attachment_mb"]) * 1024 * 1024
        for path in args.get("attachments") or []:
            path = str(path).strip(' "\'')
            if not path:
                continue
            allowed, err = self._ensure_cloud_upload_allowed(path)
            if not allowed:
                raise PermissionError(err)
            if not os.path.exists(path) or not os.path.isfile(path):
                raise FileNotFoundError(path)
            size = os.path.getsize(path)
            if size > max_bytes:
                raise ValueError(f"Attachment too large ({size} bytes): {path}")
            ctype, _ = mimetypes.guess_type(path)
            maintype, subtype = (ctype.split("/", 1) if ctype and "/" in ctype else ("application", "octet-stream"))
            with open(path, "rb") as f:
                msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(path))
        return msg, to_list + cc_list + bcc_list

    def _email_send_outbound(self, msg, recipients, save_copy=False):
        cfg = self._email_require_credentials()
        if not recipients:
            raise ValueError("No recipients resolved.")
        self._raise_if_cancelled()
        context = self._email_ssl_context()
        if cfg["smtp_ssl"]:
            if context:
                server = smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=30, context=context)
            else:
                server = smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=30)
        else:
            server = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30)
        try:
            if cfg["smtp_starttls"] and not cfg["smtp_ssl"]:
                if context:
                    server.starttls(context=context)
                else:
                    server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg, from_addr=cfg["user"], to_addrs=recipients)
        finally:
            try:
                server.quit()
            except Exception:
                pass
        if save_copy:
            self._email_append_message(cfg["sent"], msg, flags="\\Seen")

    def _email_append_message(self, mailbox, msg, flags=""):
        mail = self._email_connect_imap()
        try:
            status, data = mail.append(self._email_mailbox_arg(mailbox), flags, imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            if status != "OK":
                raise RuntimeError(f"Append failed: {data}")
            return data
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def _email_move_or_copy(self, mail, uid_set, target_mailbox, move=True):
        target = self._email_mailbox_arg(target_mailbox)
        if move:
            status, data = mail.uid("MOVE", uid_set, target)
            if status == "OK":
                return data
            status, data = mail.uid("COPY", uid_set, target)
            if status != "OK":
                raise RuntimeError(f"Move failed: {data}")
            mail.uid("STORE", uid_set, "+FLAGS.SILENT", "(\\Deleted)")
            mail.expunge()
            return data
        status, data = mail.uid("COPY", uid_set, target)
        if status != "OK":
            raise RuntimeError(f"Copy failed: {data}")
        return data

    def _email_uid_set(self, args):
        values = []
        if args.get("uid") not in (None, ""):
            values.append(args.get("uid"))
        values.extend(args.get("uids") or [])
        cleaned = [str(v).strip() for v in values if str(v).strip()]
        if not cleaned:
            raise ValueError("Missing uid/uids.")
        return ",".join(cleaned)

    def _email_unique_attachment_path(self, output_dir, filename):
        filename = safe_filename(filename or "attachment", "attachment")
        base, ext = os.path.splitext(filename)
        candidate = os.path.join(output_dir, filename)
        idx = 1
        while os.path.exists(candidate):
            candidate = os.path.join(output_dir, f"{base}_{idx}{ext}")
            idx += 1
        return candidate

    def _email_save_attachments(self, args):
        mailbox = str(args.get("mailbox") or "INBOX")
        uid = str(args.get("uid") or "").strip()
        if not uid:
            raise ValueError("save_attachments requires uid.")
        output_dir = str(args.get("output_dir") or os.path.join(self._default_output_dir(), "email_attachments")).strip(' "\'')
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(self._default_output_dir(), output_dir)
        os.makedirs(output_dir, exist_ok=True)
        selected_names = {str(n).strip() for n in (args.get("attachment_names") or []) if str(n).strip()}
        mail = self._email_connect_imap()
        try:
            self._email_select_mailbox(mail, mailbox, readonly=True)
            msg, _ = self._email_fetch_message(mail, uid)
            saved = []
            for part in msg.iter_attachments():
                filename = self._email_decode_header(part.get_filename() or "attachment")
                if selected_names and filename not in selected_names:
                    continue
                payload = part.get_payload(decode=True) or b""
                path = self._email_unique_attachment_path(output_dir, filename)
                allowed, err = self._ensure_write_allowed(path, "Saving email attachment")
                if not allowed:
                    raise PermissionError(err)
                with open(path, "wb") as f:
                    f.write(payload)
                saved.append({"filename": filename, "path": path, "size": len(payload)})
            return {"status": "ok", "uid": uid, "saved": saved}
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def _email_tool_output(self, payload, untrusted=True):
        prefix = "[UNTRUSTED_EMAIL_CONTENT]\n" if untrusted else ""
        return prefix + json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    def _email_search_one_mailbox(self, mail, mailbox, args):
        self._email_select_mailbox(mail, mailbox, readonly=True)
        search_mode = str(args.get("search_mode") or "auto").strip().lower()
        backend = "imap"
        scanned = None
        if search_mode == "scan":
            base_uids = self._email_uid_search(mail, ["ALL"])
            uids, scanned = self._email_scan_uids(mail, base_uids, args)
            backend = "local_scan"
        else:
            try:
                uids = self._email_search_uids(mail, args)
                backend = "gmail_raw" if self._email_config().get("provider") == "gmail" else "imap"
            except Exception as e:
                if search_mode != "auto":
                    raise
                logging.warning(f"Email server search failed, falling back to local scan: {e}")
                base_uids = self._email_uid_search(mail, ["ALL"])
                uids, scanned = self._email_scan_uids(mail, base_uids, args)
                backend = "local_scan_after_error"
            if search_mode == "auto" and not uids and any(args.get(k) for k in ("query", "from", "to_filter", "subject_filter", "has_attachment")):
                base_uids = self._email_uid_search(mail, ["ALL"])
                uids, scanned = self._email_scan_uids(mail, base_uids, args)
                backend = "local_scan_after_empty"

        offset = max(0, int(args.get("offset") or 0))
        try:
            count = int(args.get("count") if args.get("count") is not None else 10)
        except Exception:
            count = 10
        newest_first = list(reversed(uids))
        selected = newest_first[offset:] if count <= 0 else newest_first[offset:offset + max(1, count)]
        include_body = bool(args.get("include_body", False))
        max_body_chars = int(args.get("max_body_chars") or (1200 if include_body else 0))
        include_attachments = bool(args.get("include_attachments", False))
        records = []
        for uid in selected:
            if include_body or include_attachments:
                msg, meta = self._email_fetch_message(mail, uid)
            else:
                msg, meta = self._email_fetch_message_header(mail, uid)
            rec = self._email_record_from_message(uid, msg, meta, include_body=include_body, include_headers=False, include_attachments=include_attachments, max_body_chars=max_body_chars)
            rec["mailbox"] = mailbox
            if args.get("has_attachment") and not rec.get("attachments"):
                continue
            records.append(rec)
        return {
            "mailbox": mailbox,
            "backend": backend,
            "scanned": scanned,
            "total_matches": len(uids),
            "returned": len(records),
            "messages": records,
        }

    def _email_manager_impl(self, args):
        args = args or {}
        action = str(args.get("action", "") or "").strip().lower()
        cfg = self._email_config()
        if action == "list_folders":
            return self._email_tool_output(self._email_list_folders(), untrusted=False)
        if action in {"send", "draft", "reply", "forward"}:
            original = None
            if action in {"reply", "forward"}:
                mailbox = str(args.get("mailbox") or "INBOX")
                mail = self._email_connect_imap()
                try:
                    self._email_select_mailbox(mail, mailbox, readonly=True)
                    original, _ = self._email_fetch_message(mail, args.get("uid"))
                finally:
                    try:
                        mail.logout()
                    except Exception:
                        pass
            msg, recipients = self._email_build_outbound_message(args, original=original, mode=action)
            if action == "draft":
                self._email_append_message(cfg["drafts"], msg, flags="\\Draft")
                return self._email_tool_output({"status": "ok", "action": "draft", "mailbox": cfg["drafts"], "subject": msg.get("Subject", "")}, untrusted=False)
            self._email_send_outbound(msg, recipients, save_copy=bool(args.get("save_copy", False)))
            if action == "reply" and args.get("uid"):
                try:
                    mail = self._email_connect_imap()
                    self._email_select_mailbox(mail, str(args.get("mailbox") or "INBOX"), readonly=False)
                    mail.uid("STORE", str(args.get("uid")), "+FLAGS.SILENT", "(\\Answered)")
                    mail.logout()
                except Exception:
                    pass
            return self._email_tool_output({"status": "ok", "action": action, "sent_to": recipients, "subject": msg.get("Subject", "")}, untrusted=False)

        if action == "save_attachments":
            return self._email_tool_output(self._email_save_attachments(args), untrusted=False)

        mail = self._email_connect_imap()
        try:
            args = self._email_parse_loose_query(args)
            mailbox = str(args.get("mailbox") or "INBOX")
            if action == "create_folder":
                folder = str(args.get("folder") or "").strip()
                if not folder:
                    raise ValueError("create_folder requires folder.")
                status, data = mail.create(self._email_mailbox_arg(folder))
                if status != "OK":
                    raise RuntimeError(f"Create folder failed: {data}")
                return self._email_tool_output({"status": "ok", "action": action, "folder": folder}, untrusted=False)
            if action == "delete_folder":
                if not args.get("confirm_destructive"):
                    raise ValueError("delete_folder requires confirm_destructive=true.")
                folder = str(args.get("folder") or "").strip()
                if not folder:
                    raise ValueError("delete_folder requires folder.")
                status, data = mail.delete(self._email_mailbox_arg(folder))
                if status != "OK":
                    raise RuntimeError(f"Delete folder failed: {data}")
                return self._email_tool_output({"status": "ok", "action": action, "folder": folder}, untrusted=False)
            if action == "rename_folder":
                folder = str(args.get("folder") or "").strip()
                new_folder = str(args.get("new_folder") or "").strip()
                if not folder or not new_folder:
                    raise ValueError("rename_folder requires folder and new_folder.")
                status, data = mail.rename(self._email_mailbox_arg(folder), self._email_mailbox_arg(new_folder))
                if status != "OK":
                    raise RuntimeError(f"Rename folder failed: {data}")
                return self._email_tool_output({"status": "ok", "action": action, "folder": folder, "new_folder": new_folder}, untrusted=False)

            readonly = action in {"search", "read"}
            if action == "search":
                if args.get("all_mailboxes"):
                    search_mailboxes = self._email_list_folders_on_connection(mail)
                else:
                    search_mailboxes = [str(m).strip() for m in (args.get("mailboxes") or []) if str(m).strip()] or [mailbox]
                results = []
                total_matches = 0
                total_returned = 0
                for current_mailbox in search_mailboxes:
                    try:
                        result = self._email_search_one_mailbox(mail, current_mailbox, args)
                    except Exception as e:
                        logging.warning(f"Email search skipped mailbox {current_mailbox}: {e}")
                        continue
                    results.append(result)
                    total_matches += result["total_matches"]
                    total_returned += result["returned"]
                messages = []
                for result in results:
                    messages.extend(result["messages"])
                return self._email_tool_output({"status": "ok", "mailbox": mailbox, "searched_mailboxes": search_mailboxes, "total_matches": total_matches, "returned": total_returned, "mailbox_results": [{k: v for k, v in r.items() if k != "messages"} for r in results], "messages": messages})

            if action == "read":
                self._email_select_mailbox(mail, mailbox, readonly=readonly)
                uid_set = [str(args.get("uid")).strip()] if args.get("uid") else [str(u).strip() for u in (args.get("uids") or []) if str(u).strip()]
                if not uid_set:
                    raise ValueError("read requires uid or uids.")
                try:
                    default_body_chars = max(1200, int(self.settings.get("email_default_read_body_chars", 6000) or 6000))
                except Exception:
                    default_body_chars = 6000
                try:
                    multi_body_chars = max(800, int(self.settings.get("email_multi_read_body_chars", 3000) or 3000))
                except Exception:
                    multi_body_chars = 3000
                max_body_chars = int(args.get("max_body_chars") or (multi_body_chars if len(uid_set) > 1 else default_body_chars))
                include_headers = bool(args.get("include_headers", len(uid_set) == 1))
                records = []
                for uid in uid_set:
                    msg, meta = self._email_fetch_message(mail, uid)
                    rec = self._email_record_from_message(uid, msg, meta, include_body=bool(args.get("include_body", True)), include_headers=include_headers, include_attachments=bool(args.get("include_attachments", True)), max_body_chars=max_body_chars)
                    rec["mailbox"] = mailbox
                    records.append(rec)
                return self._email_tool_output({"status": "ok", "mailbox": mailbox, "messages": records})

            self._email_select_mailbox(mail, mailbox, readonly=False)
            uid_set = self._email_uid_set(args)
            if action == "mark_read":
                mail.uid("STORE", uid_set, "+FLAGS.SILENT", "(\\Seen)")
            elif action == "mark_unread":
                mail.uid("STORE", uid_set, "-FLAGS.SILENT", "(\\Seen)")
            elif action == "star":
                mail.uid("STORE", uid_set, "+FLAGS.SILENT", "(\\Flagged)")
            elif action == "unstar":
                mail.uid("STORE", uid_set, "-FLAGS.SILENT", "(\\Flagged)")
            elif action == "archive":
                target = str(args.get("target_mailbox") or cfg["archive"])
                self._email_move_or_copy(mail, uid_set, target, move=True)
            elif action == "trash":
                target = str(args.get("target_mailbox") or cfg["trash"])
                self._email_move_or_copy(mail, uid_set, target, move=True)
            elif action == "delete":
                if not args.get("confirm_destructive"):
                    raise ValueError("Permanent delete requires confirm_destructive=true. Use trash for reversible deletion.")
                mail.uid("STORE", uid_set, "+FLAGS.SILENT", "(\\Deleted)")
                mail.expunge()
            elif action == "move":
                target = str(args.get("target_mailbox") or "").strip()
                if not target:
                    raise ValueError("move requires target_mailbox.")
                self._email_move_or_copy(mail, uid_set, target, move=True)
            elif action == "copy":
                target = str(args.get("target_mailbox") or "").strip()
                if not target:
                    raise ValueError("copy requires target_mailbox.")
                self._email_move_or_copy(mail, uid_set, target, move=False)
            else:
                raise ValueError(f"Unsupported email action: {action}")
            return self._email_tool_output({"status": "ok", "action": action, "mailbox": mailbox, "uids": uid_set}, untrusted=False)
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def email_manager_tool(self, args):
        try:
            return self._email_manager_impl(args or {})
        except SmartiCancelled:
            raise
        except Exception as e:
            return f"ERROR: {e}"
