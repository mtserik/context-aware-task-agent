import os
import re
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional, List

from src.services.registry import get_obsidian_service
from src.services.obsidian import ObsidianService

logger = logging.getLogger("CultureService")

class CultureService:
    """
    Serviço de enriquecimento cultural e curadoria de entretenimento para a Maeve.
    Integra com Wikipedia REST API, OpenLibrary, TMDB e iTunes para buscar capas
    em alta definição (posters/box art) e metadados de filmes, séries, livros e jogos.
    Gera notas ricas no padrão 'Letterboxd / Goodreads' com fichas técnicas e reflexão crítica.
    """

    def __init__(self, obsidian_service: Optional[ObsidianService] = None):
        self._obsidian = obsidian_service
        self.tmdb_api_key = os.getenv("TMDB_API_KEY")

    @property
    def obsidian(self) -> ObsidianService:
        if self._obsidian is None:
            self._obsidian = get_obsidian_service()
        return self._obsidian

    def search_metadata(self, title: str, media_type: str = "filme") -> Dict[str, Any]:
        """
        Busca metadados e imagem/pôster em alta resolução para uma obra cultural.
        media_type aceitos: 'filme', 'serie', 'livro', 'jogo', 'podcast', 'anime'.
        """
        media_norm = media_type.lower().strip()

        # 1. Se for livro, consulta OpenLibrary prioritariamente
        if media_norm in ["livro", "book", "literatura"]:
            book_meta = self._search_openlibrary(title)
            if book_meta and book_meta.get("poster_url"):
                return book_meta

        # 2. Se for filme/série e tiver TMDB configurado
        if media_norm in ["filme", "movie", "cinema", "serie", "tv"] and self.tmdb_api_key:
            tmdb_meta = self._search_tmdb(title, media_norm)
            if tmdb_meta and tmdb_meta.get("poster_url"):
                return tmdb_meta

        # 3. Busca enciclopédica na Wikipedia (Universal: filmes, livros, jogos, anime)
        wiki_meta = self._search_wikipedia(title, media_norm)
        if wiki_meta and wiki_meta.get("poster_url"):
            return wiki_meta

        # 4. Fallback: Retorna estrutura básica com título limpo
        return {
            "title": title,
            "original_title": title,
            "year": datetime.now().year,
            "creator": "Desconhecido",
            "genres": [media_norm.capitalize()],
            "synopsis": "Sinopse não encontrada automaticamente.",
            "poster_url": None,
            "media_type": media_norm,
            "source": "manual"
        }

    def _search_wikipedia(self, query: str, media_type: str) -> Optional[Dict[str, Any]]:
        """Busca pôster e resumo via Wikipedia REST API (suporte a EN e PT)."""
        suffix_map = {
            "filme": "film",
            "movie": "film",
            "cinema": "film",
            "serie": "TV series",
            "livro": "novel",
            "book": "book",
            "jogo": "video game",
            "game": "video game",
            "anime": "anime"
        }
        suffix = suffix_map.get(media_type, "")
        search_query = f"{query} {suffix}".strip()

        for lang in ["en", "pt"]:
            try:
                search_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(search_query)}&format=json"
                req = urllib.request.Request(search_url, headers={"User-Agent": "MaeveAgent/1.0 (contact@maeve.ai)"})
                with urllib.request.urlopen(req, timeout=6) as response:
                    data = json.loads(response.read().decode("utf-8"))

                search_results = data.get("query", {}).get("search", [])
                if not search_results:
                    continue

                # Pega a melhor correspondência
                page_title = search_results[0]["title"]
                summary_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(page_title)}"
                sum_req = urllib.request.Request(summary_url, headers={"User-Agent": "MaeveAgent/1.0 (contact@maeve.ai)"})
                with urllib.request.urlopen(sum_req, timeout=6) as sum_resp:
                    sum_data = json.loads(sum_resp.read().decode("utf-8"))

                poster = sum_data.get("originalimage", {}).get("source") or sum_data.get("thumbnail", {}).get("source")
                extract = sum_data.get("extract", "")

                # Tentativa de extrair ano da descrição
                year_match = re.search(r"\b(19\d\d|20\d\d)\b", extract)
                year = int(year_match.group(1)) if year_match else datetime.now().year

                return {
                    "title": sum_data.get("title", query),
                    "original_title": page_title,
                    "year": year,
                    "creator": "Diretor/Autor na Obra",
                    "genres": [media_type.capitalize()],
                    "synopsis": extract,
                    "poster_url": poster,
                    "media_type": media_type,
                    "source": f"wikipedia_{lang}"
                }
            except Exception as e:
                logger.debug(f"Wikipedia search failed for {query} ({lang}): {e}")
                continue
        return None

    def _search_openlibrary(self, query: str) -> Optional[Dict[str, Any]]:
        """Busca capa e metadados de livros no OpenLibrary."""
        try:
            url = f"https://openlibrary.org/search.json?q={urllib.parse.quote(query)}&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "MaeveAgent/1.0 (contact@maeve.ai)"})
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))

            docs = data.get("docs", [])
            if not docs:
                return None

            doc = docs[0]
            cover_i = doc.get("cover_i")
            poster_url = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg" if cover_i else None
            authors = doc.get("author_name", ["Autor Desconhecido"])
            creator_str = ", ".join(authors[:3])
            year = doc.get("first_publish_year", datetime.now().year)

            return {
                "title": doc.get("title", query),
                "original_title": doc.get("title", query),
                "year": year,
                "creator": creator_str,
                "genres": ["Literatura", "Não-Ficção" if "history" in str(doc) else "Ficção"],
                "synopsis": f"Obra de {creator_str} publicada originalmente em {year}.",
                "poster_url": poster_url,
                "media_type": "livro",
                "source": "openlibrary"
            }
        except Exception as e:
            logger.warning(f"OpenLibrary search error for '{query}': {e}")
            return None

    def _search_tmdb(self, query: str, media_type: str) -> Optional[Dict[str, Any]]:
        """Busca metadados e pôster via The Movie Database (TMDB)."""
        try:
            endpoint = "tv" if media_type in ["serie", "tv"] else "movie"
            url = f"https://api.themoviedb.org/3/search/{endpoint}?api_key={self.tmdb_api_key}&query={urllib.parse.quote(query)}&language=pt-BR"
            req = urllib.request.Request(url, headers={"User-Agent": "MaeveAgent/1.0"})
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read().decode("utf-8"))

            results = data.get("results", [])
            if not results:
                return None

            res = results[0]
            poster_path = res.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w600_and_h900_bestv2{poster_path}" if poster_path else None
            title_field = res.get("name") if endpoint == "tv" else res.get("title")
            date_field = res.get("first_air_date") if endpoint == "tv" else res.get("release_date")
            year = int(date_field[:4]) if date_field and len(date_field) >= 4 else datetime.now().year

            return {
                "title": title_field or query,
                "original_title": res.get("original_name" if endpoint == "tv" else "original_title", query),
                "year": year,
                "creator": "Equipe de Produção TMDB",
                "genres": [media_type.capitalize()],
                "synopsis": res.get("overview", ""),
                "poster_url": poster_url,
                "media_type": media_type,
                "source": "tmdb"
            }
        except Exception as e:
            logger.warning(f"TMDB search error for '{query}': {e}")
            return None

    def format_review_markdown(
        self,
        title: str,
        media_type: str,
        review_text: str,
        rating: str,
        metadata: Dict[str, Any],
        date_str: Optional[str] = None
    ) -> str:
        """Gera o Markdown completo da nota no padrão Letterboxd / Goodreads com capa em alta resolução."""
        today = date_str or datetime.now().strftime("%Y-%m-%d")
        year = metadata.get("year") or datetime.now().year
        creator = metadata.get("creator") or "Direção / Autoria da Obra"
        synopsis = metadata.get("synopsis") or "Sinopse não disponível."
        poster_url = metadata.get("poster_url")
        genres = metadata.get("genres", [media_type.capitalize()])
        genres_yaml = "\n".join([f"  - {g.lower()}" for g in genres])
        genres_str = ", ".join(genres)

        # Poster HTML centralizado elegante
        if poster_url:
            banner_md = (
                f'<div align="center">\n'
                f'  <img src="{poster_url}" alt="Pôster de {title}" width="300" style="border-radius: 8px; box-shadow: 0 4px 14px rgba(0,0,0,0.35); margin-bottom: 16px;"/>\n'
                f'</div>\n\n'
            )
        else:
            banner_md = ""

        content = f"""---
title: "{title}"
tipo: "{media_type.lower()}"
ano: {year}
criador: "{creator}"
minha_nota: "{rating}"
status: "Concluído"
data_consumo: "{today}"
poster_url: "{poster_url or ''}"
tags:
  - entretenimento/{media_type.lower()}
  - cultura
  - pensamento-critico
  - resenha
{genres_yaml}
---

# 🎬 {title} ({year})

{banner_md}> [!ABSTRACT] **Ficha Técnica & Visão Geral**
> - **Tipo:** {media_type.capitalize()}
> - **Autoria / Direção:** {creator}
> - **Ano de Lançamento:** {year}
> - **Gêneros:** {genres_str}
> - **Avaliação do Erik:** ⭐ **{rating}**
> - **Data de Registro:** {today}

---

## 📝 Sinopse
{synopsis}

---

## 🧠 Crítica & Impressões Pessoais do Erik
{review_text}

---

## 🔍 Desconstrução & Pensamento Crítico
- **Estrutura Narrativa & Ritmo:** Como a obra conduz a atenção, organiza as viradas dramáticas e resolve o conflito central.
- **Aspectos Técnicos & Estéticos:** Uso de fotografia, iluminação, paleta de cores, trilha sonora e estilo de condução visual/literária.
- **Subtexto & Diálogo Filosófico:** Questões morais, antropológicas ou existenciais provocadas pela obra.

---

### 🔗 Conexões & Órbitas
- **MOC Central:** [[MOC - Entretenimento e Cultura]]
- **Catálogo Geral:** [[Registro de Filmes Assistidos]]
- **Prática:** Pensamento Crítico e Repertório Cultural no Segundo Cérebro
"""
        return content

    async def log_cultural_entry(
        self,
        title: str,
        media_type: str,
        review_text: str,
        rating: str = "4.5/5",
        date_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fluxo ponta a ponta: busca metadados/pôster, formata nota, grava no Vault do Obsidian
        em 'Recursos/Entretenimento/{title}.md' e atualiza o catálogo central.
        """
        try:
            # 1. Enriquecimento de metadados
            metadata = self.search_metadata(title, media_type)
            clean_title = metadata.get("title", title).replace("/", "-").replace(":", " -")
            note_filename = f"{clean_title}.md"
            relative_path = f"Recursos/Entretenimento/{note_filename}"

            # 2. Geração do Markdown com Pôster
            note_content = self.format_review_markdown(
                title=clean_title,
                media_type=media_type,
                review_text=review_text,
                rating=rating,
                metadata=metadata,
                date_str=date_str
            )

            # 3. Gravação da Nota Atômica de Resenha
            commit_msg = f"Maeve: Registrou resenha cultural de '{clean_title}' ({media_type})"
            await self.obsidian.write_note(relative_path, note_content, commit_message=commit_msg)

            # 4. Atualização do Registro Central (Registro de Filmes Assistidos / Leituras)
            await self._append_to_catalog(clean_title, media_type, rating, review_text, metadata, date_str)

            # 5. Push das alterações
            await self.obsidian.push(message=f"Maeve: Adicionou '{clean_title}' ao acervo cultural")

            return {
                "success": True,
                "message": f"Resenha de '{clean_title}' criada com sucesso com capa HD!",
                "path": relative_path,
                "poster_url": metadata.get("poster_url"),
                "title": clean_title,
                "rating": rating
            }

        except Exception as e:
            logger.error(f"Erro ao registrar resenha cultural de '{title}': {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _append_to_catalog(
        self,
        clean_title: str,
        media_type: str,
        rating: str,
        review_text: str,
        metadata: Dict[str, Any],
        date_str: Optional[str]
    ):
        """Adiciona entrada concisa no catálogo acumulador."""
        catalog_path = "Recursos/Entretenimento/Registro de Filmes Assistidos.md"
        today = date_str or datetime.now().strftime("%Y-%m-%d")
        creator = metadata.get("creator", "Desconhecido")
        genres = ", ".join(metadata.get("genres", [media_type.capitalize()]))
        synopsis = metadata.get("synopsis", "")
        if len(synopsis) > 250:
            synopsis = synopsis[:250] + "..."

        entry = f"""
## [[{clean_title}]]
- **Data:** {today}
- **Tipo:** {media_type.capitalize()}
- **Direção/Autoria:** {creator}
- **Gênero:** {genres}
- **Avaliação do Erik:** {rating}
- **Sinopse Breve:** {synopsis}
- **Resumo da Crítica:** {review_text[:300]}
- **Tags:** #{media_type.lower()} #cultura #pensamento-critico
"""
        try:
            current_content = await self.obsidian.get_note_content(catalog_path)
            # Insere antes da seção de conexões se existir
            if "### 🔗 Conexões & Órbitas" in current_content:
                parts = current_content.split("### 🔗 Conexões & Órbitas")
                updated_content = parts[0].rstrip() + "\n" + entry + "\n---\n### 🔗 Conexões & Órbitas" + parts[1]
            else:
                updated_content = current_content + "\n" + entry

            await self.obsidian.write_note(catalog_path, updated_content, commit_message=f"Maeve: Atualizou catálogo com '{clean_title}'")
        except Exception as e:
            logger.warning(f"Não foi possível atualizar catálogo acumulador '{catalog_path}': {e}")
