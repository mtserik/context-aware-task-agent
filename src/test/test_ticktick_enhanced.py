import asyncio
import os
import json
from dotenv import load_dotenv
from src.services.ticktick import TickTickService

async def test_enhanced_features():
    load_dotenv()
    service = TickTickService()
    
    print("\n🚀 [INICIANDO TESTE DE INTERFACE ENHANCED TICKTICK]")
    
    # 1. Testar Listagem de Estrutura (Pastas e Listas)
    print("\n--- 1. TESTANDO ESTRUTURA (MCP list_projects + list_project_groups) ---")
    try:
        projects_resp = await service.list_projects()
        groups_resp = await service.list_project_groups()
        
        # DEBUG RAW RESPONSES
        print(f"DEBUG: projects_resp type: {type(projects_resp)}")
        print(f"DEBUG: groups_resp type: {type(groups_resp)}")
        
        # Se vier envolto em 'projects' ou similar (comum em MCP)
        projects = projects_resp.get('projects', projects_resp) if isinstance(projects_resp, dict) else projects_resp
        groups = groups_resp.get('project_groups', groups_resp) if isinstance(groups_resp, dict) else groups_resp

        print(f"✅ Projetos encontrados: {len(projects)}")
        print(f"✅ Grupos (Pastas) encontrados: {len(groups)}")
        
        # Mapeamento para exibição bonita
        if isinstance(groups, list):
            group_map = {g['id']: g['name'] for g in groups if isinstance(g, dict) and 'id' in g}
        else:
            group_map = {}

        if isinstance(projects, list):
            for p in projects[:5]: # Mostrar apenas 5 para brevidade
                if isinstance(p, dict):
                    g_name = group_map.get(p.get('groupId'), "Sem Grupo")
                    print(f"   - Lista: {p.get('name')} (Pasta: {g_name}) [Kind: {p.get('kind')}]")
        else:
            print(f"⚠️ Projetos não é uma lista: {projects}")
            
    except Exception as e:
        print(f"❌ Erro na estrutura: {e}")
        import traceback
        traceback.print_exc()

    # 2. Criar uma Nota Temporária para Testar Leitura e Deleção
    print("\n--- 2. CRIANDO ITEM TEMPORÁRIO PARA VALIDAÇÃO ---")
    test_title = f"Teste Maeve Enhanced {os.urandom(2).hex()}"
    test_content = "Este é um conteúdo de teste profundo para validar a leitura de detalhes via MCP/REST."
    
    try:
        # Usamos o Inbox (geralmente o primeiro projeto) ou o primeiro ID encontrado
        target_project = None
        if isinstance(projects, list) and len(projects) > 0:
            target_project = projects[0].get('id') if isinstance(projects[0], dict) else None
        
        if not target_project:
            print(f"❌ Cancelando: Nenhum projeto válido encontrado. Projects: {projects}")
            return

        # Criar via REST (Fluxo já existente e estável)
        new_item = await service.create_task(title=test_title, content=test_content, project_id=target_project)
        item_id = new_item['id']
        print(f"✅ Item de teste criado: {test_title} [ID: {item_id}]")

        # 3. Testar Leitura de Detalhes (Onde o conteúdo completo é verificado)
        print("\n--- 3. TESTANDO LEITURA DE DETALHES (MCP fetch) ---")
        details = await service.get_task_by_id(item_id)
        
        fetched_content = details.get('content', '')
        print(f"✅ Título recuperado: {details.get('title')}")
        print(f"✅ Conteúdo recuperado: {fetched_content}")
        
        if fetched_content == test_content:
            print("💎 SUCESSO: O conteúdo completo foi lido corretamente!")
        else:
            print("⚠️ AVISO: O conteúdo lido diverge do enviado.")

        # 4. Testar Deleção
        print("\n--- 4. TESTANDO DELEÇÃO ---")
        success = await service.delete_task(target_project, item_id)
        if success:
            print(f"✅ Item {item_id} removido com sucesso!")
        else:
            print(f"❌ Falha ao remover item {item_id}.")

    except Exception as e:
        print(f"❌ Erro durante ciclo de vida do item: {e}")

    print("\n🏁 [FIM DOS TESTES TÉCNICOS]")

if __name__ == "__main__":
    asyncio.run(test_enhanced_features())
