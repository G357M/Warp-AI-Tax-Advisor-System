from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests


INFOHUB_DOC_ID_RE = re.compile(
    r"/workspace/document/(?P<id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)
DATE_RE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2}|\d{2}[./-]\d{2}[./-]\d{4})")
NUMBER_RE = re.compile(r"(?:N|№)\s*([0-9][0-9A-Za-z\u10A0-\u10FF/\-]*)")


@dataclass
class ListingContext:
    species: Optional[str] = None
    page: Optional[int] = None
    position: Optional[int] = None


@dataclass
class ExtractionMeta:
    method: str
    parser_version: str = "v1"
    title_confidence: str = "medium"
    warnings: List[str] = field(default_factory=list)


@dataclass
class StorageRefs:
    raw_json: str
    raw_md: Optional[str]
    raw_html: Optional[str]
    raw_links: Optional[str]
    normalized_md: str
    normalized_json: str


@dataclass
class HashRefs:
    content_md5: str


@dataclass
class InfohubExportResult:
    id: str
    source_url: str
    source_host: str
    language: str
    title: str
    title_raw: Optional[str]
    document_type: str
    document_number: Optional[str]
    authority: Optional[str]
    category: Optional[str]
    status: str
    date_published: Optional[str]
    date_effective: Optional[str]
    listing: ListingContext
    storage: StorageRefs
    hashes: HashRefs
    extraction: ExtractionMeta
    fetched_at: str
    body_markdown: str = field(repr=False)
    content: Dict[str, Any] = field(default_factory=dict, repr=False)

    def to_json_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload.pop("body_markdown", None)
        return payload

    def to_manifest_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_url": self.source_url,
            "language": self.language,
            "title": self.title,
            "document_type": self.document_type,
            "document_number": self.document_number,
            "authority": self.authority,
            "category": self.category,
            "status": self.status,
            "date_published": self.date_published,
            "fetched_at": self.fetched_at,
            "normalized_json": self.storage.normalized_json,
            "normalized_md": self.storage.normalized_md,
        }


class InfohubFirecrawlClient:
    def __init__(self, api_key: str, base_url: str = "https://api.firecrawl.dev/v2"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def scrape_url(self, url: str, formats: Optional[List[str]] = None) -> Dict[str, Any]:
        formats = formats or ["markdown", "html", "links"]
        response = requests.post(
            f"{self.base_url}/scrape",
            headers=self.headers,
            json={"url": url, "formats": formats},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()


class InfohubNormalizer:
    def __init__(self, output_root: Path):
        self.store = InfohubExportStore(output_root)

    def export_document(
        self,
        source_url: str,
        raw_payload: Dict[str, Any],
        *,
        method: str = "firecrawl",
        listing_species: Optional[str] = None,
        listing_page: Optional[int] = None,
        listing_position: Optional[int] = None,
        fetched_at: Optional[str] = None,
    ) -> InfohubExportResult:
        data = raw_payload.get("data", {}) if isinstance(raw_payload, dict) else {}
        markdown = (data.get("markdown") or "").strip()
        html = data.get("html")
        links = data.get("links") or []
        metadata = data.get("metadata") or {}
        content = data.get("content") or {}

        doc_id = self.extract_document_id(source_url)
        title_raw = self.extract_title_raw(markdown, metadata)
        title, title_confidence, title_warnings = self.extract_title(markdown, metadata)
        language = self.detect_language(markdown)
        document_type = self.infer_document_type(title, metadata)
        document_number = self.extract_document_number(title, metadata)
        authority = self.extract_authority(title, metadata)
        category = self.infer_category(title, markdown, metadata)
        date_published, date_warnings = self.extract_date_published(markdown, metadata)
        status = self.infer_status(metadata)
        warnings = title_warnings + date_warnings
        fetched_at = fetched_at or datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        content_hash = hashlib.md5(markdown.encode("utf-8")).hexdigest()
        year_bucket = self.year_bucket(date_published)

        storage = self.store.build_storage(doc_id=doc_id, language=language, document_type=document_type, year_bucket=year_bucket)

        result = InfohubExportResult(
            id=doc_id,
            source_url=source_url,
            source_host=urlparse(source_url).netloc,
            language=language,
            title=title,
            title_raw=title_raw,
            document_type=document_type,
            document_number=document_number,
            authority=authority,
            category=category,
            status=status,
            date_published=date_published,
            date_effective=None,
            listing=ListingContext(species=listing_species, page=listing_page, position=listing_position),
            storage=storage,
            hashes=HashRefs(content_md5=content_hash),
            extraction=ExtractionMeta(method=method, title_confidence=title_confidence, warnings=warnings),
            fetched_at=fetched_at,
            content=content,
            body_markdown=markdown,
        )

        self.store.write_raw(doc_id=doc_id, raw_payload=raw_payload, markdown=markdown or None, html=html, links=links)
        self.store.write_normalized(result)
        self.store.upsert_manifest(result)
        self.store.upsert_indexes(result)

        return result

    @staticmethod
    def extract_document_id(url: str) -> str:
        match = INFOHUB_DOC_ID_RE.search(url)
        if match:
            return match.group("id").lower()
        return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def detect_language(text: str) -> str:
        if re.search(r"[\u10A0-\u10FF]", text):
            return "ka"
        if re.search(r"[\u0400-\u04FF]", text):
            return "ru"
        if re.search(r"[A-Za-z]", text):
            return "en"
        return "unknown"

    @staticmethod
    def extract_title_raw(markdown: str, metadata: Dict[str, Any]) -> Optional[str]:
        raw_title = metadata.get("title") or metadata.get("ogTitle")
        if raw_title:
            return str(raw_title).strip()
        for line in markdown.splitlines():
            if line.strip():
                return line.strip()
        return None

    def extract_title(self, markdown: str, metadata: Dict[str, Any]) -> tuple[str, str, List[str]]:
        warnings: List[str] = []
        metadata_title = metadata.get("title") or metadata.get("ogTitle")
        if metadata_title:
            cleaned = str(metadata_title).strip()
            cleaned = re.sub(r"\s+-\s+infohub\.rs\.ge$", "", cleaned, flags=re.I)
            if cleaned:
                return cleaned, "high", warnings

        for line in markdown.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                cleaned = line.lstrip("#").strip()
                if cleaned:
                    warnings.append("title_from_heading_fallback")
                    return cleaned, "medium", warnings
            if len(line) > 10 and not line.startswith("[") and not line.startswith("!"):
                warnings.append("title_from_first_content_line")
                return line[:240], "low", warnings

        warnings.append("title_missing")
        return "Untitled document", "low", warnings

    @staticmethod
    def infer_document_type(title: str, metadata: Dict[str, Any]) -> str:
        lowered = " ".join(
            [
                title,
                str(metadata.get("description", "")),
                str(metadata.get("type", "")),
                str(metadata.get("baseType", "")),
                str(metadata.get("species", "")),
            ]
        ).lower()
        if "კანონპროექტ" in lowered or "bill" in lowered or "species=bill" in lowered:
            return "bill"
        if any(
            token in lowered
            for token in [
                "ფინანსთა სამინისტროს დავების გადაწყვეტილება",
                "შემოსავლების სამსახურის დავების გადაწყვეტილება",
                "დავების გადაწყვეტილ",
            ]
        ):
            return "court_decision"
        if any(
            token in lowered
            for token in [
                "საკანონმდებლო აქტში ცვლილება",
                "კოდექსში ცვლილების შეტანის შესახებ",
                "კანონში ცვლილების შეტანის შესახებ",
                "კანონში ცვლილების შეტანის თაობაზე",
                "კონსტიტუციურ კანონში ცვლილების",
            ]
        ):
            return "law"
        if any(token in lowered for token in ["კანონქვემდებარე ნორმატიული აქტი", "დადგენილება", "დადგენილებაში ცვლილება", "ბრძანებ", "მინისტრის", "მთავრობის"]):
            return "regulation"
        if any(token in lowered for token in ["დავების გადაწყვეტილ", "გადაწყვეტილ", "decision"]):
            return "court_decision"
        if "ბრძანებ" in lowered or "order" in lowered:
            return "regulation"
        if "კანონი" in lowered or "law" in lowered:
            return "law"
        if "რეგულ" in lowered or "regulation" in lowered:
            return "regulation"
        if "legislativenews" in lowered or "news" in lowered or "სიახლე" in lowered:
            return "news"
        return "guideline"

    @staticmethod
    def extract_document_number(title: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        metadata = metadata or {}
        raw_number = metadata.get("documentNumber")
        if raw_number:
            return str(raw_number).strip().strip(' -') or None
        match = NUMBER_RE.search(title)
        return match.group(1).strip().strip(' -') if match else None

    @staticmethod
    def extract_authority(title: str, metadata: Dict[str, Any]) -> Optional[str]:
        municipality_match = re.search(r"([\u10A0-\u10FF]+ მუნიციპალიტეტის საკრებულო)(?:ს)?", title)
        if municipality_match:
            return municipality_match.group(1)

        recipient_name = metadata.get("recipientName")
        ignored_role_like_recipients = {
            "კოლეგიური ორგანო",
            "სტრუქტურული ერთეულის უფლებამოსილი პირი",
            "შემოსავლების სამსახურის უფროსი/დავების საბჭოს თავმჯდომარე",
            "საკრებულო",
            "არაკლასიფიცირებული",
        }
        if recipient_name and str(recipient_name).strip() not in ignored_role_like_recipients:
            return str(recipient_name).strip()

        lowered = " ".join(
            [
                title,
                str(metadata.get("description", "")),
                str(metadata.get("type", "")),
                str(metadata.get("baseType", "")),
            ]
        ).lower()
        if "ფინანსთა სამინისტროს დავების გადაწყვეტილება" in lowered:
            return "საქართველოს ფინანსთა სამინისტრო"
        if "შემოსავლების სამსახურის დავების გადაწყვეტილება" in lowered:
            return "შემოსავლების სამსახური"

        if "საქართველოს მთავრობ" in lowered:
            return "საქართველოს მთავრობა"
        if "საქართველოს ფინანსთა მინისტრ" in lowered:
            return "საქართველოს ფინანსთა მინისტრი"
        if "საქართველოს გარემოს დაცვისა და სოფლის მეურნეობის მინისტრ" in lowered:
            return "საქართველოს გარემოს დაცვისა და სოფლის მეურნეობის მინისტრი"
        if "საქართველოს პარლამენტ" in lowered:
            return "საქართველოს პარლამენტი"
        if "ფინანსთა სამინისტრო" in lowered:
            return "საქართველოს ფინანსთა სამინისტრო"
        if "შემოსავლების სამსახურ" in lowered or "revenue service" in lowered:
            return "შემოსავლების სამსახური"

        authority_candidates = [
            "შემოსავლების სამსახური",
            "Revenue Service",
            "Министерство финансов",
        ]
        for candidate in authority_candidates:
            if candidate.lower() in title.lower():
                return candidate
        for key in ("siteName", "author", "publisher"):
            value = metadata.get(key)
            if value and str(value).strip() not in ignored_role_like_recipients:
                return str(value).strip()
        return None

    @staticmethod
    def infer_category(title: str, markdown: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        metadata = metadata or {}
        haystack = "\n".join(
            [
                title,
                markdown[:1000],
                str(metadata.get("description", "")),
                str(metadata.get("type", "")),
                str(metadata.get("baseType", "")),
            ]
        ).lower()
        if any(token in haystack for token in ["vat", "ндс", "დღგ"]):
            return "vat"
        if "საგადასახადო/საბაჟო დავა" in haystack or ("საგადასახადო" in haystack and "საბაჟო" in haystack and "დავა" in haystack):
            return "tax_customs_dispute"
        if any(token in haystack for token in ["tax", "налог", "საგადასახადო"]):
            return "tax"
        if any(token in haystack for token in ["customs", "тамож", "საბაჟო"]):
            return "customs"
        return None

    @staticmethod
    def extract_date_published(markdown: str, metadata: Dict[str, Any]) -> tuple[Optional[str], List[str]]:
        warnings: List[str] = []
        for key in ("publishedTime", "article:published_time", "date", "receiptDate", "modifiedTime"):
            value = metadata.get(key)
            if not value:
                continue
            parsed = InfohubNormalizer.normalize_date(str(value))
            if parsed:
                return parsed, warnings

        match = DATE_RE.search(markdown[:1200])
        if match:
            parsed = InfohubNormalizer.normalize_date(match.group("date"))
            if parsed:
                warnings.append("date_from_content_fallback")
                return parsed, warnings

        warnings.append("date_missing")
        return None, warnings

    @staticmethod
    def normalize_date(value: str) -> Optional[str]:
        value = value.strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", value):
            return value[:10]
        if re.match(r"\d{2}[./-]\d{2}[./-]\d{4}$", value):
            day, month, year = re.split(r"[./-]", value)
            return f"{year}-{month}-{day}"
        return None

    @staticmethod
    def year_bucket(date_published: Optional[str]) -> str:
        if date_published and re.match(r"\d{4}-\d{2}-\d{2}", date_published):
            return date_published[:4]
        return "undated"

    @staticmethod
    def infer_status(metadata: Dict[str, Any]) -> str:
        lowered = " ".join(
            [
                str(metadata.get("statusName", "")),
                str(metadata.get("statusType", "")),
            ]
        ).lower()
        if any(token in lowered for token in ["valid", "მოქმედი", "active", "executable", "ასამოქმედებელი"]):
            return "active"
        if any(token in lowered for token in ["draft", "პროექტ"]):
            return "draft"
        if any(token in lowered for token in ["superseded", "გაუქმ", "ძალადაკარგულ"]):
            return "superseded"
        return "unknown"


class InfohubExportStore:
    def __init__(self, root: Path):
        self.root = root
        self.raw_root = root / "raw"
        self.normalized_root = root / "normalized"
        self.index_root = root / "index"
        self.state_root = root / "state"

    def build_storage(self, *, doc_id: str, language: str, document_type: str, year_bucket: str) -> StorageRefs:
        raw_dir = self.raw_root / "documents" / doc_id
        normalized_dir = self.normalized_root / language / document_type / year_bucket / doc_id
        raw_dir.mkdir(parents=True, exist_ok=True)
        normalized_dir.mkdir(parents=True, exist_ok=True)
        self.index_root.mkdir(parents=True, exist_ok=True)
        self.state_root.mkdir(parents=True, exist_ok=True)

        return StorageRefs(
            raw_json=self.rel(raw_dir / "raw.json"),
            raw_md=self.rel(raw_dir / "raw.md"),
            raw_html=self.rel(raw_dir / "raw.html"),
            raw_links=self.rel(raw_dir / "links.json"),
            normalized_md=self.rel(normalized_dir / "document.md"),
            normalized_json=self.rel(normalized_dir / "document.json"),
        )

    def write_raw(
        self,
        *,
        doc_id: str,
        raw_payload: Dict[str, Any],
        markdown: Optional[str],
        html: Optional[str],
        links: Optional[List[str]],
    ) -> None:
        raw_dir = self.raw_root / "documents" / doc_id
        raw_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(raw_dir / "raw.json", raw_payload)
        if markdown:
            (raw_dir / "raw.md").write_text(markdown, encoding="utf-8")
        if html:
            (raw_dir / "raw.html").write_text(html, encoding="utf-8")
        if links is not None:
            self._write_json(raw_dir / "links.json", links)

    def write_normalized(self, result: InfohubExportResult) -> None:
        normalized_json_path = self.root / result.storage.normalized_json
        normalized_md_path = self.root / result.storage.normalized_md
        normalized_json_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(normalized_json_path, result.to_json_dict())
        normalized_md_path.write_text(self.render_markdown(result), encoding="utf-8")

    def upsert_manifest(self, result: InfohubExportResult) -> None:
        manifest_path = self.index_root / "documents.jsonl"
        existing: Dict[str, Dict[str, Any]] = {}
        if manifest_path.exists():
            for line in manifest_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                existing[obj["id"]] = obj
        existing[result.id] = result.to_manifest_dict()
        ordered = [existing[key] for key in sorted(existing.keys())]
        manifest_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in ordered) + "\n", encoding="utf-8")

    def upsert_indexes(self, result: InfohubExportResult) -> None:
        by_id_path = self.index_root / "by-id.json"
        by_url_path = self.index_root / "by-url.json"
        by_id = self._read_json(by_id_path, default={})
        by_url = self._read_json(by_url_path, default={})
        by_id[result.id] = result.storage.normalized_json
        by_url[result.source_url] = result.id
        self._write_json(by_id_path, by_id)
        self._write_json(by_url_path, by_url)

    def render_markdown(self, result: InfohubExportResult) -> str:
        frontmatter = {
            "id": result.id,
            "title": result.title,
            "language": result.language,
            "document_type": result.document_type,
            "document_number": result.document_number,
            "authority": result.authority,
            "source_url": result.source_url,
            "date_published": result.date_published,
            "species": result.listing.species,
            "listing_page": result.listing.page,
            "complexity_level": ((result.content or {}).get("complexity") or {}).get("level"),
            "fetched_at": result.fetched_at,
        }

        lines = ["---"]
        for key, value in frontmatter.items():
            if value is None:
                continue
            if isinstance(value, str):
                escaped = value.replace('"', '\\"')
                lines.append(f'{key}: "{escaped}"')
            else:
                lines.append(f"{key}: {value}")
        lines.extend(["---", "", f"# {result.title}", "", result.body_markdown.strip(), ""])
        return "\n".join(lines)

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
