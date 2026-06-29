"""Website scraping and local document/image reading tools."""
from .shared import *


class WebContentMixin:
    def _scrape_bool_arg(self, value, default=False):
        if value is None or value == "":
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        return default

    def _scrape_int_arg(self, value, default, minimum=None, maximum=None):
        try:
            number = int(float(value))
        except Exception:
            number = default
        if minimum is not None:
            number = max(minimum, number)
        if maximum is not None:
            number = min(maximum, number)
        return number

    def _scrape_float_arg(self, value, default, minimum=None, maximum=None):
        try:
            number = float(value)
        except Exception:
            number = default
        if minimum is not None:
            number = max(minimum, number)
        if maximum is not None:
            number = min(maximum, number)
        return number

    def _scrape_pattern_list(self, value):
        if not value:
            return []
        if isinstance(value, str):
            candidates = re.split(r"[\n,]+", value)
        elif isinstance(value, (list, tuple, set)):
            candidates = value
        else:
            candidates = [value]
        return [str(item).strip() for item in candidates if str(item).strip()]

    def _scrape_normalized_host(self, netloc):
        host = str(netloc or "").lower().split("@")[-1].split(":")[0].strip(".")
        return host[4:] if host.startswith("www.") else host

    def _normalize_scrape_url(self, url):
        url = html.unescape(str(url or "").strip().strip("[]()<>\"'"))
        if not url:
            return ""
        if url.startswith("//"):
            url = "https:" + url
        if not re.match(r"(?i)^https?://", url):
            url = "https://" + url
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return ""
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        return urllib.parse.urlunparse((parsed.scheme.lower(), netloc, path, "", parsed.query, ""))

    def _canonical_scrape_url(self, url):
        url = self._normalize_scrape_url(url)
        if not url:
            return ""
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if parsed.scheme == "http" and netloc.endswith(":80"):
            netloc = netloc[:-3]
        if parsed.scheme == "https" and netloc.endswith(":443"):
            netloc = netloc[:-4]
        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return urllib.parse.urlunparse((parsed.scheme, netloc, path, "", parsed.query, ""))

    def _scrape_pattern_matches(self, patterns, url):
        lower_url = str(url or "").lower()
        for pattern in patterns:
            try:
                if re.search(pattern, url, flags=re.IGNORECASE):
                    return True
            except re.error:
                if str(pattern).lower() in lower_url:
                    return True
        return False

    def _scrape_url_allowed(self, candidate_url, start_url, same_domain, include_subdomains, include_patterns, exclude_patterns):
        candidate_url = self._canonical_scrape_url(candidate_url)
        if not candidate_url:
            return False
        is_start_url = candidate_url == self._canonical_scrape_url(start_url)
        parsed = urllib.parse.urlparse(candidate_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        blocked_exts = {
            ".7z", ".apk", ".avi", ".bin", ".css", ".csv", ".dmg", ".doc", ".docx",
            ".exe", ".gif", ".gz", ".ico", ".iso", ".jpeg", ".jpg", ".js", ".json",
            ".mov", ".mp3", ".mp4", ".mpeg", ".pdf", ".png", ".ppt", ".pptx", ".rar",
            ".rss", ".svg", ".tar", ".tgz", ".wav", ".webm", ".webp", ".xls", ".xlsx",
            ".xml", ".zip"
        }
        if os.path.splitext(parsed.path.lower())[1] in blocked_exts:
            return False
        if same_domain:
            start_host = self._scrape_normalized_host(urllib.parse.urlparse(start_url).netloc)
            candidate_host = self._scrape_normalized_host(parsed.netloc)
            if include_subdomains:
                if candidate_host != start_host and not candidate_host.endswith("." + start_host):
                    return False
            elif candidate_host != start_host:
                return False
        if include_patterns and not is_start_url and not self._scrape_pattern_matches(include_patterns, candidate_url):
            return False
        if exclude_patterns and self._scrape_pattern_matches(exclude_patterns, candidate_url):
            return False
        return True

    def _scrape_robots_allowed(self, url, user_agent, headers, timeout, robots_cache):
        parsed = urllib.parse.urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in robots_cache:
            robots_cache[base] = None
            try:
                import urllib.robotparser as robotparser
                robots_url = urllib.parse.urljoin(base, "/robots.txt")
                res = self._run_cancelable_callable(lambda: self._request_get(robots_url, headers=headers, timeout=timeout))
                if getattr(res, "status_code", 599) < 400:
                    parser = robotparser.RobotFileParser()
                    parser.set_url(robots_url)
                    parser.parse((res.text or "").splitlines())
                    robots_cache[base] = parser
            except SmartiCancelled:
                raise
            except Exception:
                robots_cache[base] = None
        parser = robots_cache.get(base)
        if not parser:
            return True
        try:
            return bool(parser.can_fetch(user_agent or "*", url))
        except Exception:
            return True

    def _scrape_sitemap_urls(self, start_url, headers, timeout, limit):
        try:
            from bs4 import BeautifulSoup
            parsed = urllib.parse.urlparse(start_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            candidates = [urllib.parse.urljoin(base, "/sitemap.xml")]
            try:
                robots_url = urllib.parse.urljoin(base, "/robots.txt")
                robots_res = self._run_cancelable_callable(lambda: self._request_get(robots_url, headers=headers, timeout=timeout))
                if getattr(robots_res, "status_code", 599) < 400:
                    for line in (robots_res.text or "").splitlines():
                        if line.strip().lower().startswith("sitemap:"):
                            sitemap_url = line.split(":", 1)[1].strip()
                            if sitemap_url and sitemap_url not in candidates:
                                candidates.append(sitemap_url)
            except SmartiCancelled:
                raise
            except Exception:
                pass

            urls = []
            seen_sitemaps = set()
            idx = 0
            while idx < len(candidates) and len(urls) < limit and idx < 10:
                sitemap_url = self._canonical_scrape_url(candidates[idx])
                idx += 1
                if not sitemap_url or sitemap_url in seen_sitemaps:
                    continue
                seen_sitemaps.add(sitemap_url)
                try:
                    res = self._run_cancelable_callable(lambda: self._request_get(sitemap_url, headers=headers, timeout=timeout))
                    if getattr(res, "status_code", 599) >= 400:
                        continue
                    try:
                        from bs4 import XMLParsedAsHTMLWarning
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
                            soup = BeautifulSoup(res.text or "", "html.parser")
                    except Exception:
                        soup = BeautifulSoup(res.text or "", "html.parser")
                    for loc in soup.find_all("loc"):
                        loc_url = self._canonical_scrape_url(loc.get_text(" ", strip=True))
                        if not loc_url:
                            continue
                        if loc_url.lower().endswith(".xml") and len(candidates) < 10:
                            candidates.append(loc_url)
                        elif loc_url not in urls:
                            urls.append(loc_url)
                            if len(urls) >= limit:
                                break
                except SmartiCancelled:
                    raise
                except Exception:
                    continue
            return urls[:limit]
        except SmartiCancelled:
            raise
        except Exception:
            return []

    def _scrape_clean_text_from_soup(self, soup):
        for tag in soup(["script", "style", "noscript", "template", "svg", "canvas", "iframe", "form"]):
            tag.decompose()
        for tag in soup(["nav", "footer", "header", "aside"]):
            tag.decompose()
        for br in soup.find_all("br"):
            br.replace_with("\n")
        roots = soup.find_all(["main", "article"])
        raw = "\n".join(root.get_text("\n", strip=True) for root in roots) if roots else soup.get_text("\n", strip=True)
        lines = []
        previous = ""
        for line in raw.splitlines():
            clean = re.sub(r"\s+", " ", html.unescape(line)).strip()
            if clean and clean != previous:
                lines.append(clean)
                previous = clean
        return "\n".join(lines).strip()

    def _scrape_fetch_page(self, url, headers, timeout):
        from bs4 import BeautifulSoup
        res = self._run_cancelable_callable(lambda: self._request_get(url, headers=headers, timeout=timeout, allow_redirects=True))
        res.raise_for_status()
        content_type = str(res.headers.get("content-type", "") or "").lower()
        if content_type and not any(part in content_type for part in ("text/html", "application/xhtml", "application/xml", "text/xml")):
            return {"error": f"Unsupported content type: {content_type.split(';')[0]}", "url": url}
        if not getattr(res, "encoding", None):
            res.encoding = getattr(res, "apparent_encoding", None) or "utf-8"
        final_url = self._canonical_scrape_url(getattr(res, "url", "") or url) or self._canonical_scrape_url(url)
        soup = BeautifulSoup(res.text or "", "html.parser")
        title = ""
        if soup.title:
            title = re.sub(r"\s+", " ", soup.title.get_text(" ", strip=True)).strip()
        description = ""
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if meta_desc and meta_desc.get("content"):
            description = re.sub(r"\s+", " ", str(meta_desc.get("content") or "")).strip()
        primary_image = ""
        image_meta = soup.find(
            "meta",
            attrs={"property": re.compile(r"^og:image(?::url)?$", re.I)},
        ) or soup.find("meta", attrs={"name": re.compile(r"^twitter:image(?::src)?$", re.I)})
        if image_meta and image_meta.get("content"):
            candidate = urllib.parse.urljoin(final_url, html.unescape(str(image_meta.get("content") or "").strip()))
            parsed_image = urllib.parse.urlparse(candidate)
            if parsed_image.scheme.lower() == "https" and parsed_image.netloc:
                primary_image = candidate
        if not primary_image:
            for image_tag in soup.find_all("img", src=True):
                candidate = urllib.parse.urljoin(final_url, html.unescape(str(image_tag.get("src") or "").strip()))
                parsed_image = urllib.parse.urlparse(candidate)
                if parsed_image.scheme.lower() == "https" and parsed_image.netloc:
                    primary_image = candidate
                    break
        links = []
        seen_links = set()
        for anchor in soup.find_all("a", href=True):
            href = html.unescape(str(anchor.get("href") or "")).strip()
            if not href or href.startswith("#") or re.match(r"(?i)^(javascript|mailto|tel|sms|data):", href):
                continue
            resolved = self._canonical_scrape_url(urllib.parse.urljoin(final_url, href))
            if not resolved or resolved in seen_links:
                continue
            seen_links.add(resolved)
            label = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
            links.append({"url": resolved, "text": label[:140]})
        text = self._scrape_clean_text_from_soup(soup)
        return {
            "url": final_url,
            "title": title,
            "description": description,
            "primary_image": primary_image,
            "text": text,
            "links": links,
            "status_code": getattr(res, "status_code", None),
        }

    def _format_scrape_result(self, start_url, mode, pages, errors, discovered_links, options):
        if not pages:
            detail = "; ".join(errors[:5]) if errors else "No readable HTML pages were fetched."
            return f"ERROR: Could not read website. {detail}"

        max_total_chars = options["max_total_chars"]
        max_page_chars = options["max_page_chars"]
        include_links = options["include_links"]
        max_links = options["max_links"]
        truncated = False
        used_chars = 0
        lines = [
            "[UNTRUSTED_WEB_CONTENT]",
            (
                "SCRAPE_SUMMARY "
                f"mode={mode} start_url={start_url} pages={len(pages)} "
                f"errors={len(errors)} max_depth={options['max_depth']} max_pages={options['max_pages']}"
            ),
        ]
        if errors:
            lines.append("WARNINGS:")
            for err in errors[:8]:
                lines.append(f"- {err}")

        for idx, page in enumerate(pages, start=1):
            remaining = max_total_chars - used_chars
            if remaining <= 0:
                truncated = True
                break
            page_text = page.get("text", "") or ""
            page_limit = min(max_page_chars, remaining)
            if len(page_text) > page_limit:
                page_text = page_text[:page_limit].rstrip()
                truncated = True
            used_chars += len(page_text)
            lines.extend([
                "",
                f"--- PAGE {idx} ---",
                f"URL: {page.get('url', '')}",
                f"TITLE: {page.get('title', '') or '(no title)'}",
            ])
            if page.get("description"):
                lines.append(f"DESCRIPTION: {page.get('description')}")
            if page.get("primary_image"):
                lines.append(f"PRIMARY_IMAGE: {page.get('primary_image')}")
            lines.extend(["TEXT:", page_text or "(no visible text extracted)"])

        if include_links and discovered_links:
            lines.extend(["", f"DISCOVERED_LINKS first={min(len(discovered_links), max_links)} total={len(discovered_links)}:"])
            for link in discovered_links[:max_links]:
                label = f" | {link.get('text')}" if link.get("text") else ""
                lines.append(f"- {link.get('url', '')}{label}")

        if truncated:
            lines.append(f"\n[TRUNCATED: output limited to about {max_total_chars} text characters.]")
        return "\n".join(lines)

    def scrape_website(self, url, options=None):
        if not BS4_INSTALLED:
            return "ERROR: pip install beautifulsoup4"
        options = options or {}
        try:
            start_url = self._canonical_scrape_url(url)
            if not start_url:
                return "ERROR: Invalid or missing URL."

            mode = str(options.get("mode") or "page").strip().lower()
            if self._scrape_bool_arg(options.get("crawl"), False):
                mode = "crawl"
            if mode not in {"page", "crawl"}:
                mode = "page"

            try:
                tool_output_limit = int(self.settings.get("max_tool_output_chars", 100000) or 100000)
            except Exception:
                tool_output_limit = 100000
            default_timeout = self._timeout("network_timeout_seconds", 20)
            timeout = self._scrape_int_arg(options.get("timeout_seconds"), default_timeout, 5, 120)
            default_pages = 1 if mode == "page" else 30
            max_pages = self._scrape_int_arg(options.get("max_pages"), default_pages, 1, 200)
            if mode == "page":
                max_pages = 1
            max_depth = self._scrape_int_arg(options.get("max_depth"), 0 if mode == "page" else 2, 0, 6)
            max_total_chars = self._scrape_int_arg(options.get("max_total_chars"), 30000 if mode == "page" else 90000, 2000, max(2000, tool_output_limit - 2000))
            max_page_chars = self._scrape_int_arg(options.get("max_page_chars"), 20000 if mode == "page" else 12000, 1000, max_total_chars)
            include_links = self._scrape_bool_arg(options.get("include_links"), True)
            max_links = self._scrape_int_arg(options.get("max_links"), 80, 0, 500)
            same_domain = self._scrape_bool_arg(options.get("same_domain"), True)
            include_subdomains = self._scrape_bool_arg(options.get("include_subdomains"), False)
            respect_robots = self._scrape_bool_arg(options.get("respect_robots_txt"), True)
            use_sitemap = self._scrape_bool_arg(options.get("use_sitemap"), True)
            delay_seconds = self._scrape_float_arg(options.get("delay_seconds"), 0 if mode == "page" else 0.2, 0, 5)
            include_patterns = self._scrape_pattern_list(options.get("include_patterns"))
            exclude_patterns = self._scrape_pattern_list(options.get("exclude_patterns"))
            user_agent = str(options.get("user_agent") or "SmartiAI/1.0 (+https://local.smarti.ai) Mozilla/5.0").strip()
            headers = {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.7",
                "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            effective_options = {
                "max_pages": max_pages,
                "max_depth": max_depth,
                "max_total_chars": max_total_chars,
                "max_page_chars": max_page_chars,
                "include_links": include_links,
                "max_links": max_links,
            }

            queue = [(start_url, 0)]
            if mode == "crawl" and use_sitemap:
                for sitemap_url in self._scrape_sitemap_urls(start_url, headers, timeout, max_pages * 3):
                    if self._scrape_url_allowed(sitemap_url, start_url, same_domain, include_subdomains, include_patterns, exclude_patterns):
                        queue.append((sitemap_url, 1))

            seen = set()
            queued = {start_url}
            pages = []
            errors = []
            discovered_links = []
            discovered_seen = set()
            robots_cache = {}

            while queue and len(pages) < max_pages:
                self._raise_if_cancelled()
                current_url, depth = queue.pop(0)
                current_url = self._canonical_scrape_url(current_url)
                if not current_url or current_url in seen:
                    continue
                seen.add(current_url)
                if not self._scrape_url_allowed(current_url, start_url, same_domain, include_subdomains, include_patterns, exclude_patterns):
                    continue
                if respect_robots and not self._scrape_robots_allowed(current_url, user_agent, headers, timeout, robots_cache):
                    errors.append(f"Skipped by robots.txt: {current_url}")
                    continue
                try:
                    page = self._scrape_fetch_page(current_url, headers, timeout)
                    if page.get("error"):
                        errors.append(f"{current_url}: {page.get('error')}")
                    else:
                        page["depth"] = depth
                        pages.append(page)
                        for link in page.get("links", []):
                            link_url = self._canonical_scrape_url(link.get("url", ""))
                            if not link_url:
                                continue
                            if link_url not in discovered_seen:
                                discovered_seen.add(link_url)
                                discovered_links.append({"url": link_url, "text": link.get("text", "")})
                            if (
                                mode == "crawl"
                                and depth < max_depth
                                and link_url not in seen
                                and link_url not in queued
                                and self._scrape_url_allowed(link_url, start_url, same_domain, include_subdomains, include_patterns, exclude_patterns)
                            ):
                                queue.append((link_url, depth + 1))
                                queued.add(link_url)
                except SmartiCancelled:
                    raise
                except Exception as e:
                    errors.append(f"{current_url}: {redact_sensitive_text(str(e), self.settings)[:300]}")
                if mode == "crawl" and delay_seconds and queue and len(pages) < max_pages:
                    time.sleep(delay_seconds)

            return self._format_scrape_result(start_url, mode, pages, errors, discovered_links, effective_options)
        except SmartiCancelled:
            raise
        except Exception as e:
            return f"ERROR: {redact_sensitive_text(str(e), self.settings)}"

    def read_local_document(self, path):
        path = path.strip(' "\'')
        if not os.path.exists(path): return f"ERROR: Not found: {path}"
        sandbox_ok, sandbox_err = self._ensure_sandbox_path_allowed(path, "read")
        if not sandbox_ok: return sandbox_err
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in ['.txt', '.csv', '.md', '.json', '.py', '.pyw', '.log']:
                with open(path, 'r', encoding='utf-8', errors='replace') as f: return "[UNTRUSTED_LOCAL_FILE]\n" + f.read()[:15000]
            elif ext == '.docx':
                if not DOCX_INSTALLED: return "ERROR: pip install python-docx"
                import docx
                return "[UNTRUSTED_LOCAL_FILE]\n" + "\n".join([p.text for p in docx.Document(path).paragraphs])[:15000]
            elif ext == '.pdf':
                if not PDF_INSTALLED: return "ERROR: pip install PyPDF2"
                import PyPDF2
                text = ""
                with open(path, 'rb') as f:
                    for page in PyPDF2.PdfReader(f).pages: text += page.extract_text() + "\n"
                return "[UNTRUSTED_LOCAL_FILE]\n" + text[:15000]
            else: return f"ERROR: Unsupported format {ext}"
        except Exception as e: return f"ERROR: {e}"

    def read_local_image(self, path):
        try:
            if not os.path.exists(path): return f"ERROR: Not found"
            sandbox_ok, sandbox_err = self._ensure_sandbox_path_allowed(path, "read")
            if not sandbox_ok: return sandbox_err
            if os.path.getsize(path) > 12 * 1024 * 1024:
                return "ERROR: Image is too large for safe upload (max 12MB)."
            mime_type = guess_mime_type(path)
            with open(path, "rb") as img: return f"IMAGE_BASE64:{mime_type}:{base64.b64encode(img.read()).decode('utf-8')}"
        except Exception as e: return f"ERROR: {e}"
