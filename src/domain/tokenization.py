import re
from dataclasses import dataclass
from typing import List, Optional
import tiktoken

@dataclass
class SemanticChunk:
    """Representa um pedaço de texto fatiado com métricas precisas de tokens."""
    content: str
    token_count: int
    chunk_index: int
    total_chunks: int = 0
    header_context: str = ""

class MarkdownSemanticChunker:
    """
    Fatiador semântico de Markdown para RAG com contagem estrita via tiktoken (cl100k_base).
    Respeita fronteiras de sintaxe (parágrafos, tabelas, callouts, equações $$ e blocos de código),
    mantendo overlap calibrado entre blocos consecutivos.
    """

    def __init__(
        self,
        min_tokens: int = 300,
        target_tokens: int = 600,
        max_tokens: int = 800,
        overlap_tokens: int = 60,
        encoding_name: str = "cl100k_base"
    ):
        self.min_tokens = min_tokens
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.tokenizer = tiktoken.get_encoding(encoding_name)

    def count_tokens(self, text: str) -> int:
        """Calcula o número exato de tokens do texto."""
        return len(self.tokenizer.encode(text, disallowed_special=()))

    def chunk_markdown(self, markdown_text: str, chapter_title: Optional[str] = None) -> List[SemanticChunk]:
        """
        Segmenta o Markdown preservando a árvore sintática e limites de tokens.
        """
        if not markdown_text or not markdown_text.strip():
            return []

        # 1. Quebra preliminar em blocos atômicos (parágrafos, seções, tabelas, callouts)
        atomic_blocks = self._split_atomic_blocks(markdown_text)

        chunks_data: List[Tuple[str, int, str]] = []
        current_paragraphs: List[str] = []
        current_tokens = 0
        current_header = chapter_title or ""

        for block in atomic_blocks:
            # Se for cabeçalho, atualiza o contexto
            header_match = re.match(r'^(#{1,4})\s+(.+)$', block.strip())
            if header_match:
                current_header = header_match.group(2).strip()

            block_tokens = self.count_tokens(block)

            # Se um único bloco exceder max_tokens (ex: tabela gigante ou texto sem parágrafos)
            if block_tokens > self.max_tokens:
                # Flush do acumulador anterior se houver
                if current_paragraphs:
                    chunk_text = "\n\n".join(current_paragraphs).strip()
                    chunks_data.append((chunk_text, current_tokens, current_header))
                    current_paragraphs = []
                    current_tokens = 0

                # Fatiamento forçado por frases do bloco longo
                sub_chunks = self._split_large_block(block, self.max_tokens)
                for sc in sub_chunks:
                    sc_tokens = self.count_tokens(sc)
                    chunks_data.append((sc, sc_tokens, current_header))
                continue

            # Verifica se adicionar o bloco estoura a janela máxima
            if current_tokens + block_tokens > self.max_tokens:
                if current_paragraphs:
                    chunk_text = "\n\n".join(current_paragraphs).strip()
                    chunks_data.append((chunk_text, current_tokens, current_header))

                    # Mantém overlap: pega os últimos blocos que somem ~overlap_tokens
                    overlap_paras = []
                    overlap_acc = 0
                    for p in reversed(current_paragraphs):
                        p_toks = self.count_tokens(p)
                        if overlap_acc + p_toks <= self.overlap_tokens:
                            overlap_paras.insert(0, p)
                            overlap_acc += p_toks
                        else:
                            break

                    current_paragraphs = overlap_paras
                    current_tokens = overlap_acc

            current_paragraphs.append(block)
            current_tokens += block_tokens

        # Flush final
        if current_paragraphs:
            chunk_text = "\n\n".join(current_paragraphs).strip()
            if chunk_text:
                chunks_data.append((chunk_text, current_tokens, current_header))

        # Monta objetos SemanticChunk finais com índice total
        total = len(chunks_data)
        result: List[SemanticChunk] = []
        for idx, (txt, toks, hdr) in enumerate(chunks_data, start=1):
            result.append(SemanticChunk(
                content=txt,
                token_count=toks,
                chunk_index=idx,
                total_chunks=total,
                header_context=hdr
            ))

        return result

    def _split_atomic_blocks(self, text: str) -> List[str]:
        """
        Quebra o Markdown em blocos sem romper blocos de código (```)
        nem equações em bloco ($$...$$).
        """
        # Preserva blocos de código e fórmulas em bloco substituindo quebras internas
        lines = text.split("\n")
        blocks: List[str] = []
        current_block: List[str] = []
        in_code_block = False
        in_math_block = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
            elif stripped.startswith("$$"):
                in_math_block = not in_math_block

            if not in_code_block and not in_math_block and stripped == "":
                if current_block:
                    blocks.append("\n".join(current_block).strip())
                    current_block = []
            else:
                current_block.append(line)

        if current_block:
            blocks.append("\n".join(current_block).strip())

        return [b for b in blocks if b]

    def _split_large_block(self, block: str, max_tokens: int) -> List[str]:
        """Divide um parágrafo/bloco excepcionalmente grande por frases."""
        sentences = re.split(r'(?<=[.?!;])\s+', block)
        sub_chunks = []
        current = []
        current_toks = 0

        for s in sentences:
            s_toks = self.count_tokens(s)
            if current_toks + s_toks > max_tokens and current:
                sub_chunks.append(" ".join(current).strip())
                current = [s]
                current_toks = s_toks
            else:
                current.append(s)
                current_toks += s_toks

        if current:
            sub_chunks.append(" ".join(current).strip())

        return sub_chunks
