import os
import subprocess
import glob
import re
import yaml
from typing import List, Dict, Any

class ObsidianService:
    """
    Serviço responsável pela integração com o Vault do Obsidian via Git.
    Gerencia a sincronização (pull/push), leitura de arquivos Markdown, 
    YAML frontmatter e links.
    """
    def __init__(self):
        self.repo_url = os.getenv("OBSIDIAN_REPO_URL")
        self.vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault")
        # O arquivo no container é id_ed25519 (sem o sufixo _maeve que eu presumi antes)
        self.ssh_key_source = "/root/.ssh/id_ed25519"
        self.ssh_key_dest = "/tmp/id_ed25519_container"
        self.templates_folder = ".maeve/templates"
        
        self._setup_ssh()
        self._setup_git_user()

    def _setup_git_user(self):
        """Configura nome e email do Git para permitir commits."""
        try:
            # Verifica se já está configurado no repositório
            if os.path.exists(os.path.join(self.vault_path, ".git")):
                self._run_git(["config", "user.name", "Maeve AI Agent"])
                self._run_git(["config", "user.email", "maeve-agent@internal.local"])
                print("Identidade Git configurada para Maeve.")
        except Exception as e:
            print(f"Aviso: Não foi possível configurar o usuário Git: {e}")

    def _setup_ssh(self):
        """
        Configura a chave SSH a partir de variável de ambiente ou arquivo local.
        Prioriza a variável SSH_PRIVATE_KEY para deploy cloud.
        """
        try:
            ssh_private_key = os.getenv("SSH_PRIVATE_KEY")
            
            if ssh_private_key:
                # 1. Modo Cloud: Chave via variável de ambiente
                # Garante que o conteúdo tenha as quebras de linha corretas
                key_content = ssh_private_key.replace("\\n", "\n").strip()
                if not key_content.endswith("\n"):
                    key_content += "\n"
                
                if "-----BEGIN" not in key_content:
                    print("AVISO: SSH_PRIVATE_KEY não contém '-----BEGIN'. Verifique a formatação.")

                with open(self.ssh_key_dest, "w") as f:
                    f.write(key_content)
                
                subprocess.run(["chmod", "600", self.ssh_key_dest], check=True)
                print(f"SSH configurado via variável SSH_PRIVATE_KEY em {self.ssh_key_dest}.")
            
            elif os.path.exists(self.ssh_key_source):
                # 2. Modo Local: Chave via mapeamento de volume
                subprocess.run(["cp", self.ssh_key_source, self.ssh_key_dest], check=True)
                subprocess.run(["chmod", "600", self.ssh_key_dest], check=True)
                print(f"SSH configurado usando mapeamento local em {self.ssh_key_dest}.")
            
            else:
                print("Aviso: Nenhuma chave SSH encontrada (variável ou arquivo). Git pode falhar.")
                return

            # Configura o comando Git para usar a chave correta
            os.environ["GIT_SSH_COMMAND"] = f"ssh -i {self.ssh_key_dest} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

        except Exception as e:
            print(f"Erro ao configurar SSH: {e}")

    def _run_git(self, args: List[str]):
        """Executa um comando git no diretório do vault."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.vault_path if os.path.exists(os.path.join(self.vault_path, ".git")) else None,
                capture_output=True,
                text=True,
                check=True,
                env=os.environ
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            print(f"Erro ao executar git {' '.join(args)}: {error_msg}")
            raise e

    async def sync(self):
        """
        Garante que o repositório está clonado e atualizado.
        Implementa suporte robusto a Railway Volumes (git init em vez de git clone).
        """
        git_dir = os.path.join(self.vault_path, ".git")
        
        if not os.path.exists(git_dir):
            print(f"Inicializando repositório Obsidian em {self.vault_path}...")
            # Garante que o diretório existe
            os.makedirs(self.vault_path, exist_ok=True)
            
            try:
                # 1. git init (funciona mesmo que a pasta exista e não esteja vazia)
                subprocess.run(["git", "init"], cwd=self.vault_path, check=True)
                
                # 2. Configurar remote
                # Remove o remote se já existir (raro, mas evita erros)
                try:
                    subprocess.run(["git", "remote", "remove", "origin"], cwd=self.vault_path, capture_output=True)
                except:
                    pass
                subprocess.run(["git", "remote", "add", "origin", self.repo_url], cwd=self.vault_path, check=True)
                
                # 3. Configurar usuário Git localmente
                self._setup_git_user()
                
                # 4. Fetch e Reset (usando env para SSH_COMMAND)
                print(f"Baixando arquivos de {self.repo_url}...")
                subprocess.run(["git", "fetch", "origin"], cwd=self.vault_path, env=os.environ, check=True)
                subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=self.vault_path, check=True)
                
                print("Vault inicializado com sucesso via git init.")
            except subprocess.CalledProcessError as e:
                error_output = e.stderr.decode() if hasattr(e, 'stderr') and e.stderr else str(e)
                print(f"Erro crítico ao sincronizar vault: {error_output}")
                raise Exception(f"Falha na inicialização do Git: {error_output}")
        else:
            print("Atualizando Vault (git pull)...")
            try:
                # O pull --rebase é mais limpo para automações
                self._run_git(["pull", "--rebase", "origin", "main"])
            except Exception as e:
                print(f"Erro no pull --rebase: {e}. Tentando abortar rebase.")
                try:
                    self._run_git(["rebase", "--abort"])
                except:
                    pass
                self._run_git(["pull", "origin", "main", "--no-edit"])

    async def push(self, message: str = "Maeve Auto-update"):
        """
        Faz o commit e push das alterações locais, garantindo sincronia com o remoto.
        Implementa lógica de rebase e resolução de conflitos simples.
        """
        try:
            self._run_git(["add", "."])
            status = self._run_git(["status", "--porcelain"])
            
            if status.strip():
                self._run_git(["commit", "-m", message])
                
                # Sincronização robusta
                print("Sincronizando com o remoto antes do push (pull --rebase)...")
                try:
                    self._run_git(["pull", "--rebase", "origin", "main"])
                except Exception:
                    print("Conflito detectado ou falha no rebase. Tentando forçar resolução...")
                    try:
                        self._run_git(["rebase", "--abort"])
                    except:
                        pass
                    # Tenta pull simples com estratégia recursiva padrão
                    self._run_git(["pull", "origin", "main", "--no-edit"])
                
                self._run_git(["push", "origin", "main"])
                print(f"Alterações enviadas com sucesso: {message}")
            else:
                print("Nada para commitar.")
        except Exception as e:
            error_msg = f"FALHA CRÍTICA NO GIT: {str(e)}"
            print(error_msg)
            raise Exception(error_msg)

    async def list_all_notes(self) -> List[str]:
        """
        Retorna a lista de caminhos relativos de todos os arquivos .md no vault.
        """
        pattern = os.path.join(self.vault_path, "**", "*.md")
        abs_paths = glob.glob(pattern, recursive=True)
        return [os.path.relpath(p, self.vault_path) for p in abs_paths]

    async def get_note_metadata(self, relative_path: str) -> Dict[str, Any]:
        """
        Extrai metadados básicos de uma nota (título, pasta, links, frontmatter).
        """
        full_path = relative_path if os.path.isabs(relative_path) else os.path.join(self.vault_path, relative_path)
        if not os.path.exists(full_path):
            return {}

        title = os.path.basename(relative_path).replace(".md", "")
        folder = os.path.dirname(os.path.relpath(full_path, self.vault_path))
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extração de Frontmatter (YAML)
        frontmatter = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2]
                except Exception as e:
                    print(f"Erro ao processar YAML em {relative_path}: {e}")

        # Links [[Link]]
        links = re.findall(r"\[\[(.*?)\]\]", body)
        
        return {
            "title": title,
            "path": os.path.relpath(full_path, self.vault_path),
            "folder": folder if folder != "." else "Raiz",
            "links": list(set(links)),
            "frontmatter": frontmatter,
            "char_count": len(body)
        }

    async def get_backlinks(self, note_title: str) -> List[str]:
        """
        Encontra todas as notas que mencionam a nota atual.
        """
        backlinks = []
        notes = await self.list_all_notes()
        pattern = f"[[{note_title}]]"
        
        for note_path in notes:
            content = await self.get_note_content(note_path)
            if pattern in content:
                backlinks.append(note_path)
        
        return backlinks

    async def apply_template(self, template_name: str, variables: Dict[str, str]) -> str:
        """
        Lê um template e substitui as variáveis.
        """
        template_path = os.path.join(self.vault_path, self.templates_folder, f"{template_name}.md")
        if not os.path.exists(template_path):
            return f"Erro: Template '{template_name}' não encontrado em {self.templates_folder}"
        
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        for key, value in variables.items():
            content = content.replace(f"{{{{{key}}}}}", value)
            
        return content

    async def get_note_content(self, file_path: str) -> str:
        """
        Lê o conteúdo de uma nota Markdown. Aceita caminho absoluto ou relativo ao vault.
        """
        full_path = file_path if os.path.isabs(file_path) else os.path.join(self.vault_path, file_path)
        
        if not os.path.exists(full_path):
            return ""
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Opcional: Remover frontmatter (YAML entre ---)
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
                
        return content

    async def write_note(self, relative_path: str, content: str, commit_message: str = None) -> str:
        """
        Cria ou atualiza uma nota no vault.
        relative_path: Caminho relativo ao vault (ex: 'Inbox/MinhaNota.md')
        """
        full_path = os.path.join(self.vault_path, relative_path)
        
        # Proteção contra diretórios
        if os.path.isdir(full_path):
            raise Exception(f"Erro: '{relative_path}' é um diretório, não um arquivo.")

        # Garante que o diretório existe
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        print(f"Nota escrita em: {full_path}")
        
        if commit_message:
            await self.push(commit_message)
            
        return full_path

    async def write_note_with_frontmatter(self, relative_path: str, content: str, frontmatter: Dict[str, Any], commit_message: str = None) -> str:
        """
        Cria uma nota garantindo o bloco YAML no topo.
        """
        yaml_block = "---\n" + yaml.dump(frontmatter, allow_unicode=True) + "---\n"
        full_content = yaml_block + content
        return await self.write_note(relative_path, full_content, commit_message)

    async def list_folders(self) -> List[str]:
        """
        Lista as pastas existentes no vault (ignorando pastas ocultas como .git).
        """
        folders = []
        for entry in os.scandir(self.vault_path):
            if entry.is_dir() and not entry.name.startswith("."):
                folders.append(entry.name)
        return folders

    async def delete_item(self, relative_path: str, commit_message: str = None) -> bool:
        """
        Remove um arquivo ou pasta do vault.
        """
        full_path = os.path.join(self.vault_path, relative_path)
        if not os.path.exists(full_path):
            return False
            
        import shutil
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
            
        if commit_message:
            await self.push(commit_message)
        return True

    async def move_item(self, old_relative_path: str, new_relative_path: str, commit_message: str = None) -> bool:
        """
        Move ou renomeia um arquivo ou pasta.
        """
        old_full_path = os.path.join(self.vault_path, old_relative_path)
        new_full_path = os.path.join(self.vault_path, new_relative_path)
        
        if not os.path.exists(old_full_path):
            raise Exception(f"Caminho de origem não encontrado: {old_relative_path}")
            
        # Proteção contra movimentação de pastas raiz
        if old_relative_path.strip("/") in ["", ".", "Inbox", "Projects", "Areas", "Resources", "Archives"]:
            raise Exception(f"Operação negada: Não é permitido mover a pasta raiz '{old_relative_path}'")

        # Garante que a pasta de destino existe
        os.makedirs(os.path.dirname(new_full_path), exist_ok=True)
        
        import shutil
        try:
            shutil.move(old_full_path, new_full_path)
        except Exception as e:
            raise Exception(f"Erro ao mover: {str(e)}")
        
        if commit_message:
            await self.push(commit_message)
        return True

    async def cleanup_empty_folders(self, commit_message: str = None) -> List[str]:
        """
        Remove recursivamente todas as pastas vazias no vault, 
        preservando .git e .obsidian.
        Retorna a lista de pastas removidas.
        """
        removed_folders = []
        
        for root, dirs, files in os.walk(self.vault_path, topdown=False):
            for name in dirs:
                full_path = os.path.join(root, name)
                
                if any(part.startswith(".") for part in os.path.relpath(full_path, self.vault_path).split(os.sep)):
                    continue
                
                if not os.listdir(full_path):
                    os.rmdir(full_path)
                    removed_folders.append(os.path.relpath(full_path, self.vault_path))
        
        if removed_folders and commit_message:
            await self.push(commit_message)
            
        return removed_folders
