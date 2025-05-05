import re
import os
import json  # Para armazenar os dados localmente num arquivo JSON
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext, CommandHandler
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Caminho do arquivo que armazenará os links das planilhas
USER_SHEETS_FILE = "user_sheets.json"

# Carregar as variáveis de ambiente do arquivo .env
load_dotenv()

# Obter o token da API do Telegram a partir do arquivo .env
API_TOKEN = os.getenv("API_TOKEN")

# Verificar se o token foi carregado corretamente
if not API_TOKEN:
    raise ValueError("O token da API ('API_TOKEN') não foi encontrado no arquivo .env.")


# Função para carregar os dados das planilhas dos usuários
def load_user_sheets():
    try:
        with open(USER_SHEETS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# Função para salvar os dados das planilhas dos usuários
def save_user_sheets(user_sheets):
    with open(USER_SHEETS_FILE, "w") as f:
        json.dump(user_sheets, f)


# Inicializar os dados das planilhas
user_sheets = load_user_sheets()


# Função para acessar a planilha correta do usuário
def get_google_sheet(user_id):
    # Verificar se o usuário registrou uma planilha
    if user_id not in user_sheets:
        raise ValueError(
            "Nenhuma planilha registrada para este usuário. Use o comando /registrar para registrar sua planilha.")

    # Obter o link da planilha do usuário
    sheet_link = user_sheets[user_id]

    # Extrair o ID da planilha a partir do link
    spreadsheet_id = sheet_link.split("/d/")[1].split("/")[0]

    credenciais_path = r'C:\Users\brand\botformatador\credenciais.json'

    # Credenciais para acessar a Google Sheets API
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(credenciais_path, scope)
    client = gspread.authorize(creds)

    # Abrir a planilha pelo ID e selecionar a aba "APOSTAS"
    sheet_name = "APOSTAS"  # Mantém a aba padrão "APOSTAS"
    sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)

    return sheet


# Função para inserir dados na planilha
def insert_data_to_sheet(data):
    # Obter a planilha
    sheet = get_google_sheet(data['user_id'])

    # Obter todos os valores da planilha
    all_values = sheet.get_all_values()

    # Encontrar a primeira linha vazia na coluna B (a partir da linha 2)
    row_to_insert = 2  # Começar a busca a partir da linha 2
    while row_to_insert <= len(all_values) and all_values[row_to_insert - 1][1]:  # Coluna B é o índice 1
        row_to_insert += 1

    # Preparar os dados para serem inseridos
    values_to_insert = [
        data['bookmaker'],  # Coluna B: Casa de Aposta
        data['date'],  # Coluna C: Data
        data['ev_percentage'],  # Coluna D: EV%
        data['game_description'],  # Coluna E: Jogo
        data['bet_description'],  # Coluna F: Aposta
        data['sport'],  # Coluna G: Esporte
        data['market'],  # Coluna H: Mercado
        data['odds'],  # Coluna I: Odd
        data['stake'],  # Coluna J: Stake
    ]

    # Atualizar as células necessárias na planilha em uma única requisição
    cell_range = f"B{row_to_insert}:J{row_to_insert}"
    sheet.update(values=[values_to_insert], range_name=cell_range)

    # Formatar a célula de data como número no formato dd/mm/yyyy
    date_cell = f"C{row_to_insert}"
    sheet.format(date_cell, {"numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}})

    # Definir o valor da célula de data diretamente para garantir que seja reconhecido como número
    date_value = data['date']
    sheet.update_acell(date_cell, date_value)

    # Definir o valor da célula de data diretamente para garantir que seja reconhecido como número
    date_value = data['date']
    sheet.update_acell(date_cell, date_value)


# Função para processar a mensagem e extrair os dados
def process_message(message):
    sport = "Desconhecido"
    # Dividir a mensagem em linhas
    lines = message.split("\n")

    # A linha 11 contém o mercado, que queremos extrair
    mercado_line = lines[10]  # Linha 11 é a index 10 (indexing começa de 0)

    # Extrair o texto do mercado até o parêntese "("
    mercado = mercado_line.split("(")[0].strip()  # Remove espaços extras

    # Procurar as informações principais (EV%, Stake, odds, emoji de esporte, etc.)
    ev_percentage = re.search(r"(\d+\.\d+)% aposta de valor", message)
    stake = re.search(r"Stake: (\d+\.\d+)u", message)
    odds = re.search(r"@ (\d+\.\d+)", message)
    sport_emoji = re.search(
        r"([\U0001F3C0\U000026BD\U0001F3BE\U0001F6A9\U0001F7E8\U0001F93D\U0001F3D2\U0001F3C8\U0001F3AE"
        r"\U0001F3D0\U0001F93E\U000026BE\U0001F3CC])",  # Incluído emoji de beisebol (\U000026BE)
        message
    )
    date = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", message)  # Encontrar a data
    bookmaker = re.search(r"na (\w+)", message)  # Casa de aposta
    # Captura o nome do confronto entre duas equipes
    game_description = "Desconhecido"
    game_lines = re.findall(r"(.*\s(?:vs|x)\s.*?)(?=\s\d{2}\.\d{2}\.\d{4})", message)

    if game_lines:
        game_description = game_lines[0].strip()

    # Inicializar a descrição da aposta
    description_text = "Descrição não encontrada"
    if not description_text:
        description_text = "Descrição não encontrada"  # Defina um valor padrão caso não tenha sido encontrado

    # Capturar a descrição da aposta
    description = re.search(r"Aposta: (.+?) @", message)
    if description:
        description_text = description.group(1).strip()  # Extrai a descrição da aposta

        # Verificar se "Mais" ou "Menos" está na descrição e se "1ª Parte" está na mensagem
        primeira_parte_match = re.search(r"1ª Parte", message)  # Verificar se "1ª Parte" está na mensagem

        if "Mais" in description_text:
            if primeira_parte_match:  # Se "1ª Parte" estiver na mensagem
                mercado = f"1ª Parte - Over {mercado.split(' ')[-1]}"  # Adiciona "1ª Parte" ao mercado
            else:
                mercado = f"Over {mercado.split(' ')[-1]}"  # Caso contrário, apenas "Over"
        elif "Menos" in description_text:
            if primeira_parte_match:  # Se "1ª Parte" estiver na mensagem
                mercado = f"1ª Parte - Under {mercado.split(' ')[-1]}"  # Adiciona "1ª Parte" ao mercado
            else:
                mercado = f"Under {mercado.split(' ')[-1]}"  # Caso contrário, apenas "Under"
        # Verificar se a linha de mercado contém "Player Props" e extrair o mercado entre parênteses
        if "Player Props" in mercado_line:
            player_props_match = re.search(r"Player Props - (.+?) \((.+?)\)", mercado_line)
            if player_props_match:
                market_in_parentheses = player_props_match.group(2).strip()
                # Combinar com "Mais" ou "Menos" se estiver presente na descrição
                if "Mais" in description_text:
                    mercado = f"Mais {market_in_parentheses}"
                elif "Menos" in description_text:
                    mercado = f"Menos {market_in_parentheses}"

    # Verificar se há "Total de Cantos Asiáticos" na mensagem
    cantos_asiaticos_match = re.search(r"Total de Cantos Asiáticos", message)
    if cantos_asiaticos_match:
        # Capturar a linha de apostas
        apostas_match = re.search(r"Aposta: (.+?) @", message)
        if apostas_match:
            apostas_text = apostas_match.group(1).strip()
            # Combina "Cantos asiáticos" com a linha de apostas
            description_text = f"{apostas_text} Cantos asiáticos"
            if "Cantos" in message:
                mercado = mercado + "Cantos"

    # Verificar se há "Total de Cartões Asiáticos" na mensagem
    cartoes_asiaticos_match = re.search(r"Total de Cartões Asiáticos", message)
    if cartoes_asiaticos_match:
        # Capturar a linha de apostas
        apostas_match = re.search(r"Aposta: (.+?) @", message)
        if apostas_match:
            apostas_text = apostas_match.group(1).strip()
            # Combina "Cartões asiáticos" com a linha de apostas
            description_text = f"{apostas_text} Cartões asiáticos"
            if "Cartões Asiáticos" in message:
                mercado = mercado + "Cartões asiáticos"

    # Verificar se há "Handicap Asiático" na mensagem
    handicap_asiatico_match = re.search(r"Handicap Asiático", message)
    if handicap_asiatico_match:
        # Capturar a linha de apostas
        apostas_match = re.search(r"Aposta: (.+?) @", message)
        if apostas_match:
            apostas_text = apostas_match.group(1).strip()
            # Combina "Handicap asiático" com a linha de apostas
            description_text = f"{apostas_text} Handicap Asiático"

    # Verificar se há "Handicap Asiático" e "Cantos" na mensagem
    handicap_asiatico_cantos_match = re.search(r"Handicap Asiático - Cantos", message)
    if handicap_asiatico_cantos_match:
        # Capturar a linha de apostas
        apostas_match = re.search(r"Aposta: (.+?) @", message)
        if apostas_match:
            apostas_text = apostas_match.group(1).strip()
            # Combina "Handicap Asiático - Cantos" com a linha de apostas
            description_text = f"{apostas_text} Handicap Asiático - Cantos"
            if "Handicap Asiático - Cantos" in message:
                mercado = mercado + "Handicap Asiático - Cantos"

    # Verificar se há "Map Handicap" na mensagem
    second_map_handicap_match = re.search(r"2nd Map Handicap", message)
    if second_map_handicap_match:
        # Capturar a linha de apostas
        apostas_match = re.search(r"Aposta: (.+?) @", message)
        if apostas_match:
            apostas_text = apostas_match.group(1).strip()
            # Combina "Map Handicap" com a linha de apostas
            description_text = f"{apostas_text} 2nd Map Handicap"
    if not description_text:  # Verifica se já foi atribuída uma descrição
        map_handicap_match = re.search(r"Map Handicap", message)
        if map_handicap_match:
            # Capturar a linha de apostas
            apostas_match = re.search(r"Aposta: (.+?) @", message)
            if apostas_match:
                apostas_text = apostas_match.group(1).strip()
                # Combina "Map Handicap" com a linha de apostas
                description_text = f"{apostas_text} Map Handicap"

    # Adicionar "Maps" ao final da descrição da aposta
    if "Total Maps" in message:
        description_text = description_text + " Maps"

    if "1st Map Total Kills" in message:
        description_text = description_text + " 1st Map Kills"

    if "1st Map Total Kills" in message:
        mercado = mercado + " 1st Map"

    if "1st Map Moneyline" in message:
        description_text = description_text + " ML 1st Map"

    if "2nd Map Moneyline" in message:
        description_text = description_text + " ML 2nd Map"

    second_map_total_kills_match = re.search(r"2nd Map Total Kills", message)
    if second_map_total_kills_match:
        # Capturar a linha de apostas
        apostas_match = re.search(r"Aposta: (.+?) @", message)
        if apostas_match:
            apostas_text = apostas_match.group(1).strip()
            # Combina "2nd Map Total Kills" com a linha de apostas
            description_text = f"{apostas_text} Kills 2nd Map"
            mercado = mercado + " 2nd Map"

    # Verificar se há "1ª Parte - Handicap Asiático" na mensagem
    primeira_parte_handicap_match = re.search(r"1ª Parte - Handicap Asiático", message)
    if primeira_parte_handicap_match:
        # Capturar a linha de apostas
        apostas_match = re.search(r"Aposta: (.+?) @", message)
        if apostas_match:
            apostas_text = apostas_match.group(1).strip()
            # Combina "1ª Parte - Handicap Asiático" com a linha de apostas
            description_text = f"{apostas_text} 1ª Parte Handicap Asiático"

    # Verificar se há "1ª Parte - Golos" na mensagem
    primeira_parte_golos_match = re.search(r"1ª Parte - Golos", message)
    if primeira_parte_golos_match:
        # Capturar a linha de apostas
        apostas_match = re.search(r"Aposta: (.+?) @", message)
        if apostas_match:
            apostas_text = apostas_match.group(1).strip()
            # Combina "1ª Parte - Golos" com a linha de apostas
            description_text = f"{apostas_text} Golos 1ª Parte "
    else:
        # Verificar se há "Golos" na mensagem (apenas se "1ª Parte - Golos" não foi encontrado)
        golos_match = re.search(r"Golos", message)
        if golos_match:
            # Capturar a linha de apostas
            apostas_match = re.search(r"Aposta: (.+?) @", message)
            if apostas_match:
                apostas_text = apostas_match.group(1).strip()
                # Combina "Golos" com a linha de apostas
                description_text = f"{apostas_text} Golos"

    # Capturar Player Props
    player_props_match = re.search(r"Player Props - (.+?) \((.+?)\) \((\d+(\.\d+)?)\)", message)
    if player_props_match:
        player_name = player_props_match.group(1).strip()
        stat_type = player_props_match.group(2).strip()
        stat_value = player_props_match.group(3).strip()
        description_text = f"{player_name} {description_text} {stat_type}"  # Combine com a descrição da aposta
        description_text = f"{description_text}"  # Adiciona o valor da estatística

    # Verificar se o mercado é de "Player Props" e ajustar o esporte
    if "player props" in mercado_line.lower():
        if sport_emoji:
            # Diferenciar o esporte com base no emoji
            match sport_emoji.group(1):
                case "\U0001F3C0":  # Emoji de basquete
                    sport = "Props NBA"
                case "\U0001F3D2":  # Emoji de hóquei
                    sport = "Hóquei"
                case "\U000026BE":  # Emoji de beisebol
                    sport = "Beisebol"
                case "\U0001F3C8":  # Emoji de beisebol
                    sport = "Futebol Americano"
    else:
        # Caso não seja "Player Props", ajustar normalmente o esporte pelo emoji
        if sport_emoji:
            match sport_emoji.group(1):
                case "\U0001F3C0":
                    sport = "NBA" if "NBA" in message else "Basquete"
                case "\U0001F3D2":
                    sport = "Hóquei"
                case "\U000026BE":
                    sport = "Beisebol"
                case "\U000026BD" | "\U0001F6A9" | "\U0001F7E8":
                    sport = "Futebol"
                case "\U0001F3BE":
                    sport = "Tênis"
                case "\U0001F3C8":
                    sport = "Futebol Americano"
                case "\U0001F3AE":
                    sport = "eSports"
                case "\U0001F3D0":
                    sport = "Vôlei"
                case "\U0001F93C":
                    sport = "Luta"
                case "\U0001F93E":
                    sport = "Handebol"
                case "\U0001F3CC":
                    sport = "Golfe"

    # Substituir "Golos" por "Gols" ou "Pontos" dependendo do esporte
    if "Golos" in description_text:
        if sport == "Futebol":
            description_text = description_text.replace("Golos", "Gols")
        elif sport in ["Basquete", "NBA"]:
            description_text = description_text.replace("Golos", "Pontos")
        elif sport == "Tênis":
            description_text = description_text.replace("Golos", "Games")  # Substituir por "Games" se for Tênis

    # Substituir "Golos" por "Games" se o esporte for Tênis
    if "Golos" in mercado:
        if sport == "Futebol":
            mercado = mercado.replace("Golos", "Gols")
        elif sport in ["Basquete", "NBA"]:
            mercado = mercado.replace("Golos", "Pontos")
        elif sport == "Tênis":
            mercado = mercado.replace("Golos", "Games")  # Substituir por "Games" se for Tênis

    # Dicionário de traduções
    translations = {
        "Rebounds": "Rebotes",
        "Points": "Pontos",
        "Golos": "Gols",
        "Assists": "Assistências",
        "fouls": "faltas",
        "Shots On Goal": "SOT",
        "Receptions": "Recepções",
        "Passing Yards": "Jardas de Passe",
        "Rushing Yards": "Jardas de Corrida",
        "Tackles+Assists": "Desarmes+Assistências",
        "Receiving Yards": "Jardas de Recepção",
        "Mais": "Over",
        "Menos": "Under",
        "Interceptions": "Interceptações",
        "longest Reception": "Recepção mais longa",
        "Pass Attempts": "Tentativas de Passe",
        "Maps": "Mapas",
        "Map": "Mapa",
        "Moneyline": "Resultado Final",
        "Equipa": "Equipe",
        # Adicione mais traduções conforme necessário
    }

    #

    # Função para traduzir a descrição da aposta
    def translate_description(description: str) -> str:
        for english_word, portuguese_word in translations.items():
            description = description.replace(english_word, portuguese_word)
        return description

    # Função para traduzir o mercado
    def translate_market_in_parentheses(market_in_parentheses: str) -> str:
        for english_word, portuguese_word in translations.items():
            market_in_parentheses = market_in_parentheses.replace(english_word, portuguese_word)
        return market_in_parentheses

    # Após capturar a descrição da aposta
    description_text = translate_description(description_text)
    # Após capturar o mercado
    mercado = translate_market_in_parentheses(mercado)

    # Formatando a resposta
    if all([ev_percentage, stake, odds, sport_emoji, date, bookmaker]):
        ev_percentage = round(float(ev_percentage.group(1)))
        ev_percentage = ev_percentage / 100
        # Converte stake e odds para float
        stake = float(stake.group(1))
        odds = float(odds.group(1))

        # Formata stake: sem casas decimais se for número inteiro (ex: 1.00 → 1u)
        if stake.is_integer():
            stake_str = f"{int(stake)}"  # Retira a casa decimal
        else:
            stake_str = f"{str(stake).replace('.', ',')}"  # Troca ponto por vírgula em stake

        # Formata odds: sempre com vírgula
        odds_str = str(odds).replace('.', ',')

        date_formatted = f"{date.group(3)}-{date.group(2)}-{date.group(1)}"
        bookmaker = bookmaker.group(1)

        # Construir a mensagem formatada
        formatted_message = (
            f"Casa de Aposta: {bookmaker}\n"
            f"Data: {date_formatted}\n"
            f"EV%: {ev_percentage}\n"
            f"Jogo: {game_description}\n"
            f"Aposta: {description_text}\n"
            f"Esporte: {sport}\n"
            f"Mercado: {mercado}\n"  # Adiciona o mercado à resposta
            f"Odd: {odds}\n"
            f"Stake: {stake_str}u"
        )

        formatted_data = {
            "bookmaker": bookmaker,
            "date": date_formatted,
            "ev_percentage": ev_percentage,
            "game_description": game_description,
            "bet_description": description_text,
            "sport": sport,
            "odds": odds,
            "stake": stake,
            "market": mercado
        }

        return formatted_message.strip(), formatted_data
    return None, None


# Dicionário para armazenar o estado de cada usuário (se está em modo de registrar apostas)
user_state = {}


# Função para lidar com o comando /registrar
async def handle_registrar(update: Update, context: CallbackContext) -> None:
    user_id = str(update.message.from_user.id)  # Converte o ID para string para compatibilidade no JSON

    # Verificar se o usuário já registrou uma planilha
    if user_id in user_sheets:
        await update.message.reply_text(
            "Você já registrou uma planilha. Não é necessário registrar novamente. "
            "Se precisar alterar a planilha, entre em contato com o administrador."
        )
        return

    try:
        # Verificar se o usuário forneceu um link
        if not context.args:
            await update.message.reply_text("Por favor, envie o link da sua planilha após o comando /registrar.")
            return

        # Obter o link da planilha
        sheet_link = context.args[0]

        # Validar o link (opcional, mas recomendado)
        if "docs.google.com/spreadsheets" not in sheet_link:
            await update.message.reply_text(
                "O link fornecido não parece ser de uma planilha do Google Sheets. Tente novamente.")
            return

        # Registrar o link da planilha para o usuário
        user_sheets[user_id] = sheet_link
        save_user_sheets(user_sheets)

        await update.message.reply_text(
            "Sua planilha foi registrada com sucesso. Agora você pode usar o comando /apostas para registrar suas apostas.")
    except Exception as e:
        print(f"Erro no comando /registrar: {e}")
        await update.message.reply_text("Ocorreu um erro ao registrar sua planilha. Tente novamente mais tarde.")


async def handle_apostas(update: Update, context: CallbackContext) -> None:
    user_id = str(update.message.from_user.id)

    if user_id not in user_sheets:
        await update.message.reply_text(
            "Você ainda não registrou uma planilha. Use o comando /registrar seguido do link da sua planilha para começar."
        )
        return

    user_state[user_id] = "registrando_apostas"

    await update.message.reply_text(
        "Agora você pode começar a enviar suas apostas para serem registradas na sua planilha."
    )

async def handle_message(update: Update, context: CallbackContext) -> None:
    message = update.message.text
    user_id = str(update.message.from_user.id)

    # Saudações
    saudacoes = ["oi", "olá", "hello", "hi", "bem vindo", "ola", "oi oi"]
    if message.lower() in saudacoes:
        await update.message.reply_text("Olá, seja bem-vindo! Aqui está nossa lista de comandos:\n"
                                        "/help - Ver a lista de comandos\n"
                                        "/apostas - Registrar apostas\n")
        return

    if message.lower() == "/help":
        await update.message.reply_text(
            "/help - Ver a lista de comandos\n"
            "/apostas - Registrar apostas\n"
        )
        return

    if message.lower() == "/apostas":
        await handle_apostas(update, context)
        return

    if user_state.get(user_id) != "registrando_apostas":
        await update.message.reply_text("Digite ou selecione o comando /apostas para começar a registrar suas apostas.")
        return

    try:
        # Divide a mensagem se tiver múltiplas apostas separadas por dois \n\n
        apostas = [ap.strip() for ap in message.strip().split("\n\n\n") if ap.strip()]
        respostas = []

        for aposta in apostas:
            formatted_message, formatted_data = process_message(aposta)
            if formatted_message:
                formatted_data['user_id'] = user_id
                insert_data_to_sheet(formatted_data)
                respostas.append(formatted_message)
            else:
                await update.message.reply_text(
                    "Uma das mensagens está no formato incorreto. Verifique e tente novamente.")
                return

        # Enviar cada aposta formatada
        for resposta in respostas:
            await update.message.reply_text(resposta)

        # Mensagem final
        if len(respostas) > 1:
            await update.message.reply_text("Apostas registradas com sucesso.")
        else:
            await update.message.reply_text("Aposta registrada com sucesso.")

    except Exception as e:
        print(f"Erro ao processar a mensagem: {e}")
        await update.message.reply_text("Ocorreu um erro ao registrar sua aposta. Tente novamente mais tarde.")


# Função para configurar o comando /start
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        "Olá! 👋 Seja bem-vindo.\n\n"
        "Aqui você pode enviar suas apostas do <b>EV+ Scanner</b> diretamente para a sua <b>planilha no Google Sheets</b> 📊\n\n"
        "Antes de começar, você precisa registrar sua planilha e adicionar o nosso bot como editor.\n\n"
        "👉 <b>Como registrar sua planilha:</b>\n"
        "Envie o comando:\n"
        "/registrar link-da-sua-planilha\n\n"
        "<b>Exemplo:</b>\n"
        "/registrar https://docs.google.com/spreadsheets/d/abc123XYZ/edit\n\n"
        "Depois disso, copie o e-mail abaixo e adicione como editor da planilha:\n"
        "<code>botplanilhadorsheets@macro-key-448815-n8.iam.gserviceaccount.com</code>\n\n"
        "✅ Pronto! Agora é só usar o comando <b>/apostas</b> para começar a enviar suas apostas.\n"
        "Use <b>/help</b> para ver todos os comandos disponíveis.",
        parse_mode='HTML'
    )


# Função principal que configura o bot
def main():
    application = Application.builder().token(API_TOKEN).build()

    # Adicionar os handlers
    application.add_handler(CommandHandler("registrar", handle_registrar))
    application.add_handler(CommandHandler("apostas", handle_apostas))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", handle_message))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()


if __name__ == "__main__":
    main()