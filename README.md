# DJEN Monitor

Monitor local e simples de publicações do **Diário de Justiça Eletrônico Nacional (DJEN)** por número de OAB.

O objetivo é direto: você informa sua OAB uma vez, o programa consulta o DJEN manualmente ou todos os dias no horário escolhido e gera uma planilha Excel organizada com os resultados.

**Esta versão é exclusiva para Windows 64 bits.** Não exige Docker, servidor, navegador aberto ou banco de dados externo. A Release final também não exige que o usuário instale Python.

É seguro! Qualquer desconfiança sobre o conteúdo, só mandar o link desse repositório para sua IA de preferência que ela confere.

## Para quem só quer usar

1. Abra **Releases** no GitHub (é ali na lateral direita).
2. Baixe `DJEN-Monitor-Windows-x64.zip`.
3. Extraia o ZIP para uma pasta normal.
4. Abra `DJEN Monitor.exe`.
5. Na primeira abertura, informe o número e a UF da OAB.
6. Se quiser, informe um nome ou apelido para identificar aquela OAB. É 100% opcional e basta pressionar ENTER para deixar em branco.
7. É possível cadastrar várias inscrições, inclusive em estados diferentes.
8. Escolha a janela de busca e o horário diário.
9. Pronto.

Exemplo de cadastro:

```text
Número da OAB: 123456
UF da OAB: PR
Nome/apelido desta OAB (opcional, ENTER para pular): João
```

O menu aceita e exibe normalmente caracteres em português, inclusive acentos.

Depois da configuração inicial, o menu é semelhante a este:

```text
========================================================================
 DJEN Monitor
 OABs: João (123456/PR), 654321/SP
 Busca: últimos 5 dia(s) no mínimo
 Automático: ATIVO às 10:00
========================================================================

 [1] CONSULTAR AGORA
 [2] CONFIGURAÇÕES
 [3] AGENDAMENTO
 [4] ABRIR PLANILHAS
 [5] AJUDA / DIAGNÓSTICO
 [0] SAIR
```

Não é preciso deixar o programa aberto.

## O que ele faz

- consulta a API pública do Comunica PJe/DJEN por OAB e UF;
- aceita várias OABs;
- permite um nome ou apelido opcional para cada inscrição;
- consulta uma janela configurável de dias;
- amplia automaticamente a coleta quando a última execução completa é mais antiga que essa janela;
- testa variantes comuns da inscrição quando necessário;
- pagina os resultados e aplica novas tentativas para falhas temporárias;
- rejeita localmente resultados que tragam outra OAB explicitamente;
- nunca transforma resposta incompleta em um falso "zero publicações";
- deduplica comunicações já vistas usando SQLite local;
- detecta comunicações atualizadas, reprocessadas, inativadas ou canceladas;
- gera Excel em toda execução;
- pode executar automaticamente pelo Agendador de Tarefas do Windows;
- não envia telemetria e não possui servidor próprio.

## Planilhas

Por padrão os arquivos são salvos em:

```text
Documentos\DJEN Monitor\
```

Se o Windows, OneDrive ou Controlled Folder Access impedir a gravação em Documentos, o programa usa automaticamente uma pasta segura no perfil local do usuário. A opção **ABRIR PLANILHAS** abre a pasta realmente utilizada na última execução.

Cada arquivo começa pela aba `RESUMO`, com contadores e atalhos, e contém:

- `RESUMO`
- `NOVAS_PUBLICACOES`
- `TODAS_ENCONTRADAS`
- `POSSIVEL_PRAZO`
- `REVISAR`
- `ROTINA`

Nas abas de publicações, **Inteiro teor** aparece como a 3ª coluna. O cabeçalho permanece congelado, sem congelamento vertical de colunas.

As abas de publicações foram desenhadas para leitura humana. Ao abrir o arquivo, ficam visíveis primeiro os campos úteis para o trabalho diário:

- classificação;
- situação da coleta;
- data de disponibilização;
- processo;
- tribunal e órgão julgador;
- tipo de comunicação;
- OAB monitorada, com o nome opcional configurado;
- advogado(s) encontrado(s) na própria publicação;
- partes;
- motivo da classificação;
- texto legível da publicação;
- botão/link para o inteiro teor;
- botão/link para consulta no DJEN.

Os dados técnicos não foram removidos. Identificador, hash, OAB retornada pela fonte, status, URL original, texto integral original e demais campos permanecem no mesmo arquivo em colunas ocultas à direita. Elas podem ser reexibidas no Excel quando necessário.

O texto mostrado na coluna principal é limpo de marcação HTML para facilitar a leitura. O texto integral original continua preservado nas colunas técnicas, inclusive quando precisa ser dividido por causa do limite de caracteres por célula do Excel.

A planilha também:

- usa cores diferentes para `POSSÍVEL PRAZO`, `REVISAR` e `ROTINA`;
- destaca `NOVA`, `ATUALIZADA`, `JÁ CONHECIDA` e `SEM HISTÓRICO`;
- mantém filtros de tabela;
- congela cabeçalho e colunas principais durante a rolagem;
- mostra links com textos curtos em vez de URLs gigantes;
- preserva URLs completas em colunas técnicas;
- protege células contra formula injection proveniente de texto externo.

## Nome ou apelido da OAB

O nome é apenas um rótulo local para facilitar o uso quando existem várias inscrições.

Exemplos:

```text
João (123456/PR)
Maria (98765/SP)
654321/SC
```

Ele não é enviado à API e não substitui o nome do advogado retornado pelo DJEN. O programa mantém separados:

1. nome/apelido configurado localmente;
2. OAB usada na consulta;
3. nome e OAB efetivamente retornados pela publicação.

Para alterar depois, use **CONFIGURAÇÕES > Alterar nome/apelido de uma OAB**.

## Se o histórico local falhar

O SQLite serve apenas para saber o que já apareceu antes. Se esse arquivo estiver corrompido, bloqueado ou inacessível, o programa não descarta os dados recebidos do DJEN.

Ele tenta gerar uma planilha de emergência com os itens encontrados, marcando-os como:

```text
SEM HISTÓRICO
REVISAR
```

Nesse caso ele não afirma que a publicação é nova, porque não conseguiu consultar o histórico local.

## Agendamento no Windows

O programa cria uma tarefa do próprio usuário no **Agendador de Tarefas do Windows**. A tarefa:

- roda diariamente no horário escolhido;
- usa o mesmo `DJEN Monitor.exe` em modo automático e silencioso;
- permite execução na bateria;
- não interrompe a consulta se o notebook passar para bateria;
- aceita iniciar depois do horário se a execução programada foi perdida;
- impede duas instâncias automáticas simultâneas;
- tenta reiniciar até 3 vezes, com intervalo de 15 minutos, quando a coleta termina com erro ou incompleta;
- tem limite de 2 horas por execução.

O programa não acorda o computador do modo de suspensão. A tarefa usa logon interativo para não armazenar senha. A janela configurada funciona como janela mínima: se a última execução completa for mais antiga, o programa amplia automaticamente a próxima busca para cobrir o intervalo perdido.

A criação ou remoção da tarefa pode pedir confirmação do UAC. O DJEN Monitor não solicita nem armazena a senha do Windows.

## Onde ficam os dados locais

Configuração, histórico e logs ficam no perfil local do Windows:

```text
%LOCALAPPDATA%\DJEN Monitor\
```

A configuração contém as OABs cadastradas e os nomes opcionais. Nada disso é colocado no código-fonte ou enviado a um servidor do projeto.

## Atualização

Baixe uma Release nova e abra o novo `DJEN Monitor.exe`.

A configuração antiga continua compatível. Instalações criadas antes da existência do campo de nome continuam funcionando e simplesmente deixam o nome em branco até o usuário decidir preenchê-lo.

Se o agendamento já existir, o programa atualiza a cópia interna usada pela tarefa.

## Windows SmartScreen

Builds comunitários sem assinatura Authenticode podem receber aviso do Windows SmartScreen. Isso não pode ser eliminado corretamente apenas com código. Uma distribuição sem esse tipo de aviso exige assinatura de código com certificado confiável e reputação adequada.

Confira sempre se o arquivo veio da página oficial de Releases deste repositório.

## Importante para uso jurídico

O DJEN Monitor é uma ferramenta auxiliar de coleta e organização. Ele não substitui a consulta oficial, o acompanhamento processual ou a análise profissional do advogado.

As categorias `POSSIVEL_PRAZO`, `REVISAR` e `ROTINA` são regras automáticas de triagem. Nenhuma delas afirma definitivamente que existe ou não existe prazo, e nenhum item é descartado por classificação.

Em caso de coleta incompleta, erro de API, divergência de OAB ou ausência de campos relevantes, o programa sinaliza a situação na planilha.

Fontes oficiais:

- Portal Comunica PJe: https://comunica.pje.jus.br/
- API/Swagger Comunica PJe: https://comunicaapi.pje.jus.br/swagger/index.html

## Privacidade

O programa é local. Ele envia para a API consultada apenas os parâmetros necessários para a pesquisa, como OAB, UF e período. Não possui analytics, conta de usuário, servidor próprio ou telemetria.

Os resultados podem conter dados pessoais existentes em publicações judiciais. Proteja as planilhas e o perfil do Windows de acordo com as regras aplicáveis ao seu uso profissional.

## Desenvolvedores

Requisitos para trabalhar com o código-fonte:

```text
Python 3.11+
Windows 64 bits para validar o executável final e o Agendador de Tarefas
```

Instalação de desenvolvimento:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e . -r requirements-dev.txt
python -m pytest
```

Teste opcional contra a API real:

```powershell
python tools\live_smoke.py NUMERO UF
```

## CI e Release

O GitHub Actions no Windows executa:

1. compilação de todo o Python;
2. testes unitários e de integração;
3. registro e remoção de uma tarefa temporária no Agendador do Windows;
4. build real do `DJEN Monitor.exe` com PyInstaller;
5. autoteste do executável sem console;
6. autoteste da cópia estável usada pelo agendamento;
7. autoteste do console em UTF-8, incluindo caracteres acentuados.

Uma tag `v*` gera:

```text
DJEN-Monitor-Windows-x64.zip
```

## Licença

MIT.
