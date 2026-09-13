import os
import zlib
import zipfile
import xml.etree.ElementTree as ET
import olefile
from pypdf import PdfReader

class DocumentParser:
    """HWP, HWPX, PDF 파일 텍스트 추출기"""

    @classmethod
    def extract_text(cls, file_path: str, max_chars: int = 15000) -> str:
        if not os.path.exists(file_path):
            return ""
        
        ext = os.path.splitext(file_path)[-1].lower()
        try:
            if ext == ".hwp":
                text = cls._parse_hwp(file_path)
            elif ext == ".hwpx":
                text = cls._parse_hwpx(file_path)
            elif ext == ".pdf":
                text = cls._parse_pdf(file_path)
            elif ext in [".txt", ".md"]:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            else:
                return ""
            
            # 토큰 절약을 위한 길이 제한
            return text.strip()[:max_chars]
        except Exception as e:
            print(f"[Warn] 파일 파싱 실패 ({file_path}): {e}")
            return ""

    @staticmethod
    def _parse_hwp(file_path: str) -> str:
        """구버전 OLE 기반 HWP 파일 텍스트 추출"""
        if not olefile.isOleFile(file_path):
            return ""
        
        ole = olefile.OleFileIO(file_path)
        dirs = ole.listdir()
        sections = [d for d in dirs if d[0] == "BodyText" and d[1].startswith("Section")]
        sections.sort(key=lambda x: int(x[1].replace("Section", "")))

        full_text = []
        for section in sections:
            stream = ole.openstream(section)
            data = stream.read()
            try:
                # Deflate 압축 해제 시도
                unpacked = zlib.decompress(data, -15)
            except Exception:
                unpacked = data
            
            # UTF-16LE 텍스트 디코딩 및 제어문자 필터링
            text = unpacked.decode("utf-16le", errors="ignore")
            cleaned = "".join(c for c in text if c.isprintable() or c in "\n\t ")
            full_text.append(cleaned)
        
        ole.close()
        return "\n".join(full_text)

    @staticmethod
    def _parse_hwpx(file_path: str) -> str:
        """신규 zip/xml 기반 HWPX 파일 텍스트 추출"""
        texts = []
        with zipfile.ZipFile(file_path, "r") as z:
            section_files = [f for f in z.namelist() if f.startswith("Contents/section") and f.endswith(".xml")]
            for sec_file in sorted(section_files):
                xml_data = z.read(sec_file)
                root = ET.fromstring(xml_data)
                for elem in root.iter():
                    if elem.text:
                        texts.append(elem.text.strip())
        return " ".join([t for t in texts if t])

    @staticmethod
    def _parse_pdf(file_path: str) -> str:
        """PDF 파일 텍스트 추출"""
        reader = PdfReader(file_path)
        texts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
        return "\n".join(texts)
