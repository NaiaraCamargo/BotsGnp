import traceback
from pncp_bot_material_escolar.controllers.controle_botpncp import bot

if __name__ == "__main__":
    try:
        bot(
            plataforma="materialescolar",
            mostrar_browser=False
        )
    except Exception as e:
        print("ERRO FATAL AO INICIAR O BOT:")
        print(e)
        traceback.print_exc()
        input("Pressione Enter para fechar...")