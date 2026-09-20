import os
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from src.services.book_parser.base import BookMode

logger = logging.getLogger("BookModeDetector")

class BookModeDetector:
    """
    Detector Heurístico Determinístico de Modo de Livro (Zero-Token).
    Classifica a obra em BookMode (MATH, RPG, NARRATIVE ou GENERAL) em < 100 ms
    através de 3 camadas de inspeção:
      1. Camada 0: Contexto de Path e Hints explícitas.
      2. Camada 1: Scanner Léxico de Outlines / TOC (Índice estruturado).
      3. Camada 2: Profiler Físico e Tipográfico de Amostras de Páginas.
    """

    RPG_KEYWORDS = {
        "personagem", "perícias", "pericias", "atributos", "combate",
        "ameaças", "ameacas", "bestiário", "bestiario", "rituais", "magias",
        "equipamento", "mestre", "campanha", "classes", "origens", "sanidade",
        "dificuldade do teste", "rolagem", "rolagens", "modificadores",
        "inventário", "inventario", "grimório", "grimorio", "monstros",
        "ficha de personagem", "pontos de esforço", "pontos de vida"
    }

    MATH_KEYWORDS = {
        "teorema", "demonstração", "demonstracao", "lema", "corolário", "corolario",
        "definição", "definicao", "espaços métricos", "espacos metricos", "topologia",
        "cálculo", "calculo", "integrais", "derivadas", "álgebra", "algebra",
        "matrizes", "probabilidade", "hipótese", "hipotese", "proposição", "proposicao",
        "exercícios propostos", "exercicios propostos", "espaço vetorial", "espaco vetorial",
        "convergência", "convergencia", "autovalores", "continuidade"
    }

    LATEX_FONT_HINTS = [
        "cmsy", "cmmi", "cmr", "ams", "latinmodern", "stix", "times-math",
        "computermodern", "eufm", "msam", "msbm"
    ]

    MATH_UNICODE_CHARS = set("∀∃∈∉⊆⊂∪∩∫∬∭∮∑∏√∝∞∠∧∨¬⇒⇔≡≠≤≥≦≧±∓×÷·∇∂ℝℂℕℤℚ")

    @classmethod
    def detect_mode(
        cls,
        file_path: str,
        filename: Optional[str] = None,
        hint_mode: Optional[str] = None
    ) -> Tuple[BookMode, Dict[str, Any]]:
        """
        Ponto de entrada principal. Executa as camadas de classificação e retorna
        o BookMode vencedor juntamente com os scores de diagnóstico explicativos.
        """
        fname = filename or os.path.basename(file_path)
        diagnostics = {
            "filename": fname,
            "layer0_hint": None,
            "layer1_toc_scores": {},
            "layer2_physical_scores": {},
            "final_scores": {"rpg": 0.0, "math": 0.0, "narrative": 0.0},
            "selected_mode": BookMode.GENERAL,
            "reason": ""
        }

        # ---------------------------------------------------------
        # Camada 0: Path & Explicit Hints
        # ---------------------------------------------------------
        if hint_mode:
            norm_hint = hint_mode.lower().strip()
            for mode_candidate in BookMode:
                if mode_candidate.value == norm_hint:
                    diagnostics["selected_mode"] = mode_candidate
                    diagnostics["reason"] = f"Modo forçado explicitamente via parâmetro '{hint_mode}'."
                    return mode_candidate, diagnostics

        lower_path = file_path.lower().replace("\\", "/")
        combined_target = f"{lower_path} {fname.lower()}"
        if any(k in combined_target for k in ["/rpg", "rpgs", "-rpg", "_rpg", " rpg"]):
            diagnostics["final_scores"]["rpg"] += 3.5
            diagnostics["layer0_hint"] = "Caminho ou nome do arquivo contém indicação de RPG."
        elif any(k in combined_target for k in ["imecc", "matematica", "analise", "calculo", "algebra", "probabilidade"]):
            diagnostics["final_scores"]["math"] += 3.0
            diagnostics["layer0_hint"] = "Caminho ou nome do arquivo contém indicação acadêmica/matemática."

        # Identifica extensão
        ext = os.path.splitext(fname.lower())[1]

        if ext == ".pdf":
            cls._detect_pdf(file_path, diagnostics)
        elif ext in [".epub", ".mobi"]:
            cls._detect_epub(file_path, diagnostics)
        else:
            diagnostics["reason"] = f"Extensão '{ext}' tratada com perfil genérico."

        # Decisão ponderada final
        rpg_score = diagnostics["final_scores"]["rpg"]
        math_score = diagnostics["final_scores"]["math"]
        narrative_score = diagnostics["final_scores"]["narrative"]

        if rpg_score >= 3.5 and rpg_score > math_score:
            selected = BookMode.RPG
            reason = f"Classificado como RPG (Score RPG: {rpg_score:.1f} vs Math: {math_score:.1f})"
        elif math_score >= 3.5 and math_score > rpg_score:
            selected = BookMode.MATH
            reason = f"Classificado como Matemática (Score Math: {math_score:.1f} vs RPG: {rpg_score:.1f})"
        elif narrative_score >= 2.0 and rpg_score < 2.0 and math_score < 2.0:
            selected = BookMode.NARRATIVE
            reason = f"Classificado como Narrativa/Ficção (Texto corrido contínuo, Score: {narrative_score:.1f})"
        elif rpg_score >= 2.0:
            selected = BookMode.RPG
            reason = f"Classificado como RPG por presença moderada de sinais de regras/diagramação ({rpg_score:.1f})"
        elif math_score >= 2.0:
            selected = BookMode.MATH
            reason = f"Classificado como Matemática por presença de notação científica ({math_score:.1f})"
        else:
            selected = BookMode.GENERAL
            reason = "Perfil balanceado/neutro. Modo Geral adotado."

        diagnostics["selected_mode"] = selected
        diagnostics["reason"] = reason
        logger.info(f"BookModeDetector para '{fname}': {selected.value} ({reason})")
        return selected, diagnostics

    @classmethod
    def _detect_pdf(cls, file_path: str, diagnostics: Dict[str, Any]):
        """Executa Camada 1 (TOC) e Camada 2 (Páginas) em arquivos PDF usando PyMuPDF."""
        try:
            import fitz
        except ImportError:
            logger.warning("PyMuPDF (fitz) não disponível para detecção de modo.")
            return

        try:
            doc = fitz.open(file_path)
        except Exception as e:
            logger.error(f"Erro ao abrir PDF para detecção: {e}")
            return

        total_pages = len(doc)
        diagnostics["total_pages"] = total_pages

        # ---------------------------------------------------------
        # Camada 1: Scanner Léxico de TOC (Outlines)
        # ---------------------------------------------------------
        toc = doc.get_toc() or []
        toc_text = " ".join([entry[1].lower() for entry in toc if len(entry) > 1])

        toc_rpg_matches = sum(1 for kw in cls.RPG_KEYWORDS if kw in toc_text)
        toc_math_matches = sum(1 for kw in cls.MATH_KEYWORDS if kw in toc_text)

        diagnostics["layer1_toc_scores"] = {
            "toc_entries": len(toc),
            "rpg_matches": toc_rpg_matches,
            "math_matches": toc_math_matches
        }

        if toc_rpg_matches >= 3:
            diagnostics["final_scores"]["rpg"] += min(toc_rpg_matches * 1.5, 6.0)
        if toc_math_matches >= 3:
            diagnostics["final_scores"]["math"] += min(toc_math_matches * 1.5, 6.0)

        # ---------------------------------------------------------
        # Camada 2: Profiler Físico e Tipográfico de Amostras
        # ---------------------------------------------------------
        # Sorteia até 5 páginas distribuídas entre 15% e 85% do livro
        if total_pages <= 5:
            sample_indices = list(range(total_pages))
        else:
            step = max(1, (total_pages - 1) // 5)
            sample_indices = [int(total_pages * pct) for pct in [0.15, 0.35, 0.50, 0.70, 0.85]]
            sample_indices = [max(0, min(total_pages - 1, idx)) for idx in sample_indices]
            sample_indices = sorted(list(set(sample_indices)))

        total_images = 0
        multi_column_pages = 0
        math_symbol_hits = 0
        latex_font_hits = 0
        total_word_count = 0

        for p_idx in sample_indices:
            page = doc[p_idx]
            page_rect = page.rect
            page_width = page_rect.width

            # 1. Contagem de imagens na página
            page_images = page.get_images()
            total_images += len(page_images)

            # 2. Detecção geométrica de colunas (blocks)
            blocks = page.get_text("blocks")
            col1_blocks = 0
            col2_blocks = 0

            for b in blocks:
                # b = (x0, y0, x1, y1, text, block_no, block_type)
                if len(b) >= 7 and b[6] == 0:  # Bloco de texto
                    x0, x1 = b[0], b[2]
                    # Coluna esquerda típica: x1 < 55% da largura
                    if x1 <= page_width * 0.55:
                        col1_blocks += 1
                    # Coluna direita típica: x0 >= 45% da largura
                    elif x0 >= page_width * 0.45:
                        col2_blocks += 1

            if col1_blocks >= 2 and col2_blocks >= 2:
                multi_column_pages += 1

            # 3. Análise textual da página
            page_text = page.get_text()
            words = page_text.split()
            total_word_count += len(words)

            # Símbolos matemáticos Unicode
            math_symbol_hits += sum(1 for ch in page_text if ch in cls.MATH_UNICODE_CHARS)

            # Fontes tipográficas LaTeX
            try:
                page_fonts = page.get_fonts()
                for font_entry in page_fonts:
                    font_name = font_entry[3].lower() if len(font_entry) > 3 else ""
                    if any(fh in font_name for fh in cls.LATEX_FONT_HINTS):
                        latex_font_hits += 1
            except Exception:
                pass

        sample_count = len(sample_indices) or 1
        avg_images_per_page = total_images / sample_count
        avg_words_per_page = total_word_count / sample_count

        diagnostics["layer2_physical_scores"] = {
            "sample_pages": sample_indices,
            "avg_images_per_page": round(avg_images_per_page, 2),
            "multi_column_pages": multi_column_pages,
            "math_symbol_hits": math_symbol_hits,
            "latex_font_hits": latex_font_hits,
            "avg_words_per_page": round(avg_words_per_page, 1)
        }

        # Pontuações da Camada 2
        # A) Sinais de RPG
        if avg_images_per_page >= 2.5:
            diagnostics["final_scores"]["rpg"] += 2.5
        elif avg_images_per_page >= 1.5:
            diagnostics["final_scores"]["rpg"] += 1.0

        if multi_column_pages >= (sample_count // 2):
            diagnostics["final_scores"]["rpg"] += 2.5

        # B) Sinais de Matemática
        if latex_font_hits >= 2:
            diagnostics["final_scores"]["math"] += 3.0
        if math_symbol_hits >= 15:
            diagnostics["final_scores"]["math"] += 3.0
        elif math_symbol_hits >= 5:
            diagnostics["final_scores"]["math"] += 1.5

        # C) Sinais de Narrativa (muitas palavras, poucas imagens, coluna única)
        if avg_words_per_page >= 250 and avg_images_per_page < 0.5 and multi_column_pages == 0:
            diagnostics["final_scores"]["narrative"] += 2.5

        doc.close()

    @classmethod
    def _detect_epub(cls, file_path: str, diagnostics: Dict[str, Any]):
        """Executa detecção para arquivos EPUB inspecionando metadados e estrutura HTML."""
        try:
            import ebooklib
            from ebooklib import epub
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("ebooklib ou bs4 não disponível para detecção de EPUB.")
            return

        try:
            book = epub.read_epub(file_path)
            title = book.get_metadata("DC", "title")
            diagnostics["title"] = title[0][0] if title else ""
            
            # Análise de texto dos primeiros documentos
            items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
            combined_text = ""
            for it in items[:5]:
                soup = BeautifulSoup(it.get_content(), "html.parser")
                combined_text += " " + soup.get_text().lower()

            rpg_matches = sum(1 for kw in cls.RPG_KEYWORDS if kw in combined_text)
            math_matches = sum(1 for kw in cls.MATH_KEYWORDS if kw in combined_text)

            diagnostics["final_scores"]["rpg"] += rpg_matches * 0.8
            diagnostics["final_scores"]["math"] += math_matches * 0.8

            # Se for texto predominantemente corrido sem termos técnicos de RPG ou Math
            if len(combined_text.split()) > 2000 and rpg_matches == 0 and math_matches == 0:
                diagnostics["final_scores"]["narrative"] += 3.0

        except Exception as e:
            logger.error(f"Erro ao detectar modo em EPUB: {e}")
