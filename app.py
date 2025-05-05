from flask import Flask, render_template, request, jsonify, session, url_for
from dotenv import load_dotenv
import os
import hltv_api.main as hltv
from openai import OpenAI # Importado
import json
import uuid # Importar para gerar IDs únicos para as conversas

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Cria o cliente da OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) # Cliente definido aqui!

conversations = {}

# Mensagem inicial padrão para novas conversas
INITIAL_SYSTEM_MESSAGE = {
    "role": "system",
    "content": "Você é um fã muito apaixonado do time de CS2 da FURIA, sempre empolgado quando o assunto é FURIA no Counter Strike. "
    "Use os dados disponíveis para responder perguntas sobre o time e o cenário de Counter Strike. Você só conhece dados relacionados ao cenário de Counter Strike e a organização de eSports brasileira FURIA. "
    "Você de começo só sabe que o ID da FURIA para as pesquisas na api da HLTV, que é 8297. Priorize muito usar a API da HLTV para obter dados relacionados ao cenário de Counter Strike 2, mas se não encontrar nada pesquisar na web mesmo. "
    "Tente organizar os dados da API da HLTV nas respostas para deixar o mais intuitivo de entender, e usando gírias ocasionalmente. Nunca cite ou indique que está usando alguma API. Se for usar emoji, use apenas emojis preto e branco. "
    "Leve em conta na suas respostas a data atual ao responder sobre partidas mais recentes e futuras de um time ou jogador."
}

functions = [
    {
        "name": "get_team_info",
        "description": "Obtem informações detalhadas sobre um time de CS2, o que inclui os jogadores atuais do time, jogadores que jogaram pelo time antes, partidas futuras e passadas do time, estatísticas atuais do time, ID do time, nome do time e sua URL na HLTV",
        "parameters": {
            "type": "object",
            "properties": {
                "teamid": {
                    "type": "integer",
                    "description": "ID numérico do time no HLTV."
                }
            },
            "required": ["teamid"]
        }
    },
    {
        "name": "get_players",
        "description": "Retorna jogadores atuais de um time via ID",
        "parameters": {
            "type": "object",
            "properties": {
                "teamid": {
                    "type": "integer",
                    "description": "ID numérico do time no HLTV."
                }
            },
            "required": ["teamid"]
        }
    },
    {
        "name": "top5teams",
        "description": "Retorna os 5 melhores times de CS2 de acordo com o ranking da HLTV.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "top30teams",
        "description": "Retorna os 30 melhores times de CS2 de acordo com o ranking da HLTV, incluindo jogadores. Esta função pode ser útil para descobrir o id dos outros times além da FURIA",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "top_players",
        "description": "Retorna os melhores jogadores de CS2 de acordo com as estatísticas da HLTV.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_matches",
        "description": "Retorna uma lista dos próximos jogos de CS2 da HLTV. Use quando é necessário ver as partidas mais recentes de CS2 em geral",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_results",
        "description": "Retorna uma lista dos resultados recentes de jogos de CS2 da HLTV.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_results_by_date",
        "description": "Retorna resultados de jogos de CS2 em um intervalo de datas específico.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Data de início no formato YYYY-MM-DD."
                },
                "end_date": {
                    "type": "string",
                    "description": "Data de término no formato YYYY-MM-DD."
                }
            },
            "required": ["start_date", "end_date"]
        }
    },
    {
        "name": "get_match_countdown",
        "description": "Retorna a contagem regressiva para um jogo específico usando o ID da partida.",
        "parameters": {
            "type": "object",
            "properties": {
                "match_id": {
                    "type": "integer",
                    "description": "ID numérico da partida no HLTV."
                }
            },
            "required": ["match_id"]
        }
    }
]

function_map = {
    "get_team_info": hltv.get_team_info,
    "get_players": hltv.get_players,
    "top5teams": hltv.top5teams,
    "top30teams": hltv.top30teams,
    "top_players": hltv.top_players,
    "get_matches": hltv.get_matches,
    "get_results": hltv.get_results,
    "get_results_by_date": hltv.get_results_by_date,
    "get_match_countdown": hltv.get_match_countdown
}

# Helper para obter os dados da sessão, criando se necessário
def get_session_data(session_id):
    if session_id not in conversations:
        # Se a sessão é nova ou reiniciada, cria a estrutura inicial
        new_convo_id = str(uuid.uuid4()) # Gera um ID único para a primeira conversa
        conversations[session_id] = {
            'current_convo_id': new_convo_id,
            'conversations': {
                new_convo_id: [INITIAL_SYSTEM_MESSAGE.copy()] # Começa com a mensagem do sistema
            }
        }
        print(f"Nova sessão {session_id} criada com conversa inicial: {new_convo_id}")
    return conversations[session_id]

# Rota principal para a Landing Page
@app.route("/")
def index_page():
    # Esta rota não precisa de lógica complexa de sessão/conversas
    # apenas garante que uma sessão exista antes de ir para o chat
    if "session_id" not in session:
         session["session_id"] = os.urandom(8).hex()
         print(f"Nova sessão criada via index: {session['session_id']}")
    return render_template("index.html")

# Rota para servir a página do Chat
@app.route("/chat_page")
def chat_page():
    session_id = session.get("session_id")
    if not session_id:
        # Cria um ID de sessão se não existir
        session["session_id"] = os.urandom(8).hex()
        print(f"Nova sessão criada via chat_page: {session['session_id']}")

    # Garante que a estrutura de conversas exista para esta sessão
    # get_session_data(session["session_id"]) # Chamado implicitamente no chat ou history, mas pode ser aqui também para garantir

    print(f"Acessando chat_page para sessão: {session['session_id']}")
    return render_template("chat.html")

# Rota da API do Chat (recebe POST do Javascript)
@app.route("/chat", methods=["POST"])
def chat_api():
    if "session_id" not in session:
        return jsonify({"reply": "Erro: Sessão não encontrada. Por favor, recarregue a página."}), 400

    session_id = session["session_id"]
    session_data = get_session_data(session_id)
    current_convo_id = session_data['current_convo_id']
    current_conversation = session_data['conversations'][current_convo_id]


    try:
        user_input = request.json["message"]
    except (TypeError, KeyError):
        return jsonify({"reply": "Erro: Requisição inválida."}), 400

    # Adiciona a mensagem do usuário à conversa ATUAL
    current_conversation.append({"role": "user", "content": user_input})
    print(f"Sessão {session_id}, Convo {current_convo_id} - Input: {user_input}")

    try:
        # Passa a conversa ATUAL para a API da OpenAI
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=current_conversation, # Usa a conversa atual
            functions=functions,
            function_call="auto"
        )

        message = response.choices[0].message

        if message.function_call:
            function_name = message.function_call.name

            try:
                arguments = json.loads(message.function_call.arguments)
            except json.JSONDecodeError as e:
                print(f"Sessão {session_id}, Convo {current_convo_id} - Erro ao decodificar argumentos JSON para a função {function_name}: {e}")
                return jsonify({
                    "reply": "Desculpe, houve um erro interno ao processar os argumentos da função solicitada pela IA. Por favor, tente reformular a pergunta."
                }), 500

            if function_name in function_map:
                try:
                    print(f"Sessão {session_id}, Convo {current_convo_id} - Chamando função: {function_name} com args: {arguments}")
                    function_response = function_map[function_name](**arguments)
                    print(f"Sessão {session_id}, Convo {current_convo_id} - Resposta função: {function_response}")

                    # Adiciona a chamada de função E a resposta da função à conversa ATUAL
                    current_conversation.append(message)
                    current_conversation.append({
                        "role": "function",
                        "name": function_name,
                        "content": json.dumps(function_response)
                    })

                    # Segunda chamada para a IA interpretar a resposta da função (fluxo de sucesso)
                    second_response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=current_conversation # Usa a conversa atual com a resposta da função
                    )
                    bot_reply = second_response.choices[0].message.content
                    # Adiciona a resposta da IA à conversa ATUAL
                    current_conversation.append({"role": "assistant", "content": bot_reply})

                except Exception as e:
                    print(f"Sessão {session_id}, Convo {current_convo_id} - Erro ao executar função backend {function_name}: {e}")
                    # Não chama a API novamente, retorna erro direto
                    return jsonify({
                        "reply": f"Desculpe, houve um erro ao obter os dados solicitados da HLTV (Detalhe técnico: {type(e).__name__}). Por favor, tente novamente mais tarde."
                    }), 500

            else:
                # Função solicitada pela IA não existe no nosso backend
                bot_reply = f"Desculpe, a função '{function_name}' solicitada não foi encontrada."
                print(f"Sessão {session_id}, Convo {current_convo_id} - Função não implementada: {function_name}")
                # Adiciona a chamada de função e a resposta de erro à conversa ATUAL
                current_conversation.append(message)
                current_conversation.append({
                         "role": "function",
                         "name": function_name,
                         "content": json.dumps({"error": f"Função '{function_name}' não implementada no backend."})
                    })
                # A resposta para o usuário já foi definida acima, não precisa da segunda chamada.

        else:
            # Resposta direta sem function call
            bot_reply = message.content
            # Adiciona a resposta da IA à conversa ATUAL
            current_conversation.append({"role": "assistant", "content": bot_reply})

        print(f"Sessão {session_id}, Convo {current_convo_id} - Resposta: {bot_reply}")
        return jsonify({"reply": bot_reply})

    except Exception as e:
        print(f"Sessão {session_id}, Convo {current_convo_id} - Erro geral durante a chamada da API OpenAI ou processamento: {e}")
        return jsonify({"reply": "Ocorreu um erro inesperado ao processar sua solicitação. Por favor, tente novamente."}), 500

# Rota para listar resumos das conversas (para o histórico lateral)
@app.route("/history", methods=["GET"])
def list_conversations():
    if "session_id" not in session:
        # Retorna 400 ou uma lista vazia, dependendo de como o frontend espera
        return jsonify({'conversations': [], 'current_convo_id': None}), 400

    session_id = session["session_id"]
    session_data = get_session_data(session_id) # Garante que a estrutura exista

    conversations_list = []
    # Percorre todas as conversas desta sessão
    # sorted(session_data['conversations'].items()) # Opcional: ordenar por ID ou timestamp se guardasse timestamp
    # Podemos ordenar pela ordem de criação se soubermos ela, por enquanto a ordem no dict é arbitrária
    for convo_id, messages in session_data['conversations'].items():
        # Encontra a primeira mensagem do usuário para usar como título
        first_user_message = next((msg for msg in messages if msg['role'] == 'user'), None)
        title = "Nova Conversa" # Título padrão se não houver mensagem de usuário
        if first_user_message:
            title = first_user_message['content'][:50] # Limita o título a 50 caracteres
            if len(first_user_message['content']) > 50:
                title += '...'
        conversations_list.append({
            'id': convo_id,
            'title': title
        })

    # Retorna a lista de resumos E o ID da conversa atual
    # O frontend usará isso para saber qual conversa destacar e carregar por padrão
    return jsonify({
        'conversations': conversations_list,
        'current_convo_id': session_data['current_convo_id']
    })

# Nova rota para obter mensagens de uma conversa específica
@app.route("/get_conversation/<convo_id>", methods=["GET"])
def get_conversation(convo_id):
    if "session_id" not in session:
        return jsonify({"error": "Sessão não encontrada."}), 400

    session_id = session["session_id"]
    session_data = get_session_data(session_id)

    # Verifica se o convo_id solicitado existe para esta sessão
    if convo_id not in session_data['conversations']:
        print(f"Sessão {session_id} - Convo ID {convo_id} não encontrado.")
        return jsonify({"error": "Conversa não encontrada."}), 404

    # Define a conversa solicitada como a conversa atual (Isso é importante para o /chat)
    session_data['current_convo_id'] = convo_id
    print(f"Sessão {session_id} - Definindo conversa {convo_id} como atual.")

    # Retorna as mensagens da conversa solicitada
    return jsonify(session_data['conversations'][convo_id])

# Nova rota para criar uma nova conversa
@app.route("/new_conversation", methods=["POST"])
def new_conversation():
     if "session_id" not in session:
        return jsonify({"error": "Sessão não encontrada."}), 400

     session_id = session["session_id"]
     session_data = get_session_data(session_id)

     # Cria um novo ID de conversa
     new_convo_id = str(uuid.uuid4())

     # Adiciona a nova conversa (com mensagem do sistema) ao dicionário
     session_data['conversations'][new_convo_id] = [INITIAL_SYSTEM_MESSAGE.copy()]

     # Define a nova conversa como a conversa atual para esta sessão
     session_data['current_convo_id'] = new_convo_id

     print(f"Sessão {session_id} - Nova conversa criada com ID: {new_convo_id}")

     # Retorna o ID da nova conversa criada e as mensagens iniciais
     # O frontend usará 'messages' para exibir o chat box da conversa nova
     return jsonify({'new_convo_id': new_convo_id, 'messages': session_data['conversations'][new_convo_id]})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)