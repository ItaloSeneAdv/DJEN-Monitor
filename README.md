# DJEN Monitor

Monitor local e simples de publicações do **Diário de Justiça Eletrônico Nacional (DJEN)** por número de OAB.

Você informa sua OAB uma vez, o programa consulta o DJEN manualmente ou todos os dias no horário escolhido e gera uma planilha Excel organizada com os resultados. É possível cadastrar várias inscrições, inclusive em estados diferentes.

A v1.0.1 suporta **Windows 64 bits** e **macOS**, com pacotes separados para Macs Intel e Apple Silicon. A Release final não exige Python, Docker, servidor ou navegador aberto.

## Para quem só quer usar

Abra **Releases** e baixe o arquivo correspondente ao seu computador:

- Windows 64 bits: `DJEN-Monitor-Windows-x64.zip`
- Mac Intel: `DJEN-Monitor-macOS-Intel.zip`
- Mac com Apple Silicon, incluindo M1, M2, M3, M4 e posteriores: `DJEN-Monitor-macOS-Apple-Silicon.zip`

### Windows

1. Extraia o ZIP.
2. Abra `DJEN Monitor.exe`.
3. Na primeira abertura, informe a OAB, UF e, se quiser, um nome ou apelido.
4. Escolha a janela mínima de busca e o horário diário.
5. Pronto. O programa não precisa ficar aberto para a consulta agendada.

### macOS

1. Extraia o ZIP inteiro.
2. Abra `ABRIR_DJEN_MONITOR.command`.
3. Na primeira abertura, informe a OAB, UF e, se quiser, um nome ou apelido.
4. Escolha a janela mínima de busca e o horário diário.
5. O agendamento usa o `launchd` do macOS e não exige que o programa fique aberto.

O build do macOS é assinado de forma ad-hoc para validar a integridade do binário, mas não é notarizado pela Apple. Por isso, na primeira abertura o Gatekeeper pode bloquear o arquivo. Nesse caso, confira que o ZIP veio desta página oficial de Releases e use **Ajustes do Sistema > Privacidade e Segurança > Abrir Mesmo Assim**.

Exemplo de cadastro:

```text
Número da OAB: 123456
UF da OAB: PR
Nome/apelido desta OAB (opcional, ENTER para pular): João
```

O menu aceita caracteres em português, inclusive acentos.

## O que ele faz

- consulta a API pública do Comunica PJe/DJEN por OAB e UF;
- aceita várias OABs e um nome ou apelido opcional para cada inscrição;
- consulta uma janela configurável de dias;
- amplia automaticamente a coleta quando a última execução completa é mais antiga que essa janela;
- testa variantes comuns da inscrição quando necessário;
- pagina os resultados e aplica novas tentativas para falhas temporárias;
- rejeita localmente resultados que tragam outra OAB explicitamente;
- nunca transforma resposta incompleta em um falso "zero publicações";
- deduplica comunicações já vistas usando SQLite local;
- detecta comunicações atualizadas, reprocessadas, inativadas ou canceladas;
- gera um arquivo Excel em toda execução;
- executa automaticamente pelo Agendador de Tarefas no Windows ou pelo `launchd` no macOS;
- não envia telemetria e não possui servidor próprio.

## Planilhas

Por padrão:

```text
Windows: Documentos\DJEN Monitor\
macOS:   ~/Documents/DJEN Monitor/
```

Se a pasta padrão não puder ser usada, o programa tenta uma pasta local segura no perfil do usuário. A opção **ABRIR PLANILHAS** abre a pasta realmente utilizada na última execução.

Cada arquivo contém:

- `RESUMO`
- `NOVAS_PUBLICACOES`
- `TODAS_ENCONTRADAS`
- `POSSIVEL_PRAZO`
- `REVISAR`
- `ROTINA`

Nas abas de publicações, **Inteiro teor** é a 3ª coluna. O cabeçalho fica congelado sem divisor vertical. Os filtros são filtros normais da planilha, sem tabelas estruturadas redundantes, para manter compatibilidade com o Excel desktop.

Os campos principais ficam visíveis. Identificador, hash, OAB retornada pela fonte, status, URL original, texto integral original e demais dados técnicos continuam preservados em colunas ocultas à direita e podem ser reexibidos no Excel.

Textos maiores que o limite de uma célula são divididos em colunas técnicas sem perda do conteúdo original. Caracteres XML inválidos são neutralizados e valores externos são protegidos contra formula injection.

## Classificação

As categorias `POSSIVEL_PRAZO`, `REVISAR` e `ROTINA` são regras automáticas de triagem. Nenhuma delas afirma definitivamente que existe ou não existe prazo e nenhum item é descartado por classificação.

Se o histórico SQLite estiver indisponível, o programa tenta preservar os resultados em uma planilha de emergência e sinaliza os itens para revisão, em vez de afirmar que são novos.

## Agendamento no Windows

O programa cria uma tarefa do próprio usuário no **Agendador de Tarefas do Windows**. Ela:

- roda diariamente no horário escolhido;
- usa uma cópia estável do `DJEN Monitor.exe` em modo automático;
- permite execução na bateria;
- aceita iniciar depois do horário se a execução programada foi perdida;
- impede instâncias automáticas simultâneas;
- tenta reiniciar até 3 vezes, com intervalo de 15 minutos;
- tem limite de 2 horas por execução.

A criação ou remoção pode pedir confirmação do UAC. O programa não solicita nem armazena a senha do Windows.

## Agendamento no macOS

O programa cria:

```text
~/Library/LaunchAgents/br.italosene.djenmonitor.plist
```

O `launchd` chama uma cópia estável do binário no horário escolhido. Saída e erros do processo agendado ficam nos logs locais do aplicativo. Alterar o horário recria o agente de forma controlada e desativar o agendamento descarrega e remove o plist.

## Onde ficam os dados locais

Windows:

```text
%LOCALAPPDATA%\DJEN Monitor\
```

macOS:

```text
~/Library/Application Support/DJEN Monitor/
```

Ali ficam configuração, banco de deduplicação, logs e a cópia usada pelo agendamento. A configuração contém as OABs e nomes opcionais. Nada disso é colocado no código-fonte ou enviado a um servidor do projeto.

A Release do Windows inclui `REMOVER_DADOS.bat`. A Release do macOS inclui `REMOVER_DADOS.command`. Ambos removem configuração, histórico, logs e agendamento e perguntam separadamente antes de apagar as planilhas.

## Atualização

Baixe a nova Release e abra o novo executável. A configuração anterior continua compatível. Se o agendamento já existir, o programa atualiza a cópia interna usada pela tarefa quando necessário.

## Avisos do sistema operacional

### Windows SmartScreen

Builds comunitários sem assinatura Authenticode podem receber aviso do Windows SmartScreen. Eliminar corretamente esse aviso exige certificado de assinatura de código e reputação adequada.

### macOS Gatekeeper

Sem Developer ID e notarização da Apple, o macOS pode exigir confirmação manual na primeira abertura. A assinatura ad-hoc usada no CI verifica a consistência do binário, mas não substitui notarização.

Em ambos os casos, baixe somente da página oficial de Releases deste repositório.

## Importante para uso jurídico

O DJEN Monitor é uma ferramenta auxiliar de coleta e organização. Ele não substitui a consulta oficial, o acompanhamento processual ou a análise profissional do advogado.

Em caso de coleta incompleta, erro de API, divergência de OAB ou ausência de campos relevantes, o programa sinaliza a situação em vez de esconder o item.

Fontes oficiais:

- Portal Comunica PJe: https://comunica.pje.jus.br/
- API/Swagger Comunica PJe: https://comunicaapi.pje.jus.br/swagger/index.html

## Privacidade

O programa é local. Ele envia para a API consultada apenas os parâmetros necessários para a pesquisa, como OAB, UF e período. Não possui analytics, conta de usuário, servidor próprio ou telemetria.

Os resultados podem conter dados pessoais existentes em publicações judiciais. Proteja as planilhas e o perfil do sistema operacional de acordo com as regras aplicáveis ao seu uso profissional.

## Desenvolvimento e validação

Requisitos do código-fonte:

```text
Python 3.11+
```

Os testes de CI usam Python 3.12.

No Windows, o CI valida testes unitários e de integração, registro/remoção de tarefa temporária, build PyInstaller, autoteste do EXE, cópia estável e console UTF-8.

No macOS, o CI executa a suíte completa separadamente em **x86_64** e **arm64**, valida sintaxe dos scripts `.command`, compila o binário real, executa `--self-test`, confirma a arquitetura Mach-O, aplica assinatura ad-hoc e verifica a assinatura antes de gerar os ZIPs.

Uma tag `v*` pode publicar os três assets:

```text
DJEN-Monitor-Windows-x64.zip
DJEN-Monitor-macOS-Intel.zip
DJEN-Monitor-macOS-Apple-Silicon.zip
```

## Licença

MIT.
