Para gerar os executáveis:
pyinstaller bot_pncpnew.py --onefile      
pyinstaller bot_pncpobra.py --onefile  
pyinstaller --add-data "gerar_planilha_seguro.html;." gerar_planilha_seguro.py --onefile --noconsole  
pyinstaller --add-data "gerar_planilha_obra.html;." gerar_planilha_obra.py --onefile --noconsole 
   
 Para acessar o venv:  
   venv\Scripts\activate  

Precisa ter os programas locais:
  GHOST SCRIPT
  Pandoc
  UnRAR
