# Administração

Como gerenciar usuários, grupos e permissões.

---

## Os dois tipos de administrador

Esta é a parte que mais gera dúvida, então vale começar por ela. O sistema tem
**duas noções diferentes** de administrador:

### Administrador do sistema (`is_admin`)

Uma marca no usuário, ligada **apenas** pelo script `create_user.py`. Ela dá
acesso à área de administração — criar grupos, criar usuários, gerenciar
membros.

Ela **não** dá poder sobre o conteúdo de ninguém.

### Administrador do grupo

Quem **criou** aquele grupo. Tem poder total sobre o conteúdo dele: pode editar
e apagar compromissos e anotações de qualquer membro, além de alterar o grupo e
sua lista de membros.

### Por que a distinção importa

Imagine que você criou o grupo "Vendas" e cadastrou a Maria como usuária. Ao
adicioná-la ao grupo, ela passa a ver todos os compromissos e anotações e a
criar os dela — mas não pode alterar nem apagar o que é dos outros. Quem manda
no conteúdo do grupo "Vendas" é quem o criou: você.

Ser administrador do sistema não mudaria isso. A regra completa, em uma frase:
**quem pode alterar um compromisso ou uma anotação é o autor dele ou o
administrador daquele grupo** — nunca a marca de administrador por si só.

### Administradores não entram em grupos alheios

Cada administrador só pode adicionar aos seus grupos os usuários que ele mesmo
cadastrou. Como administradores são criados apenas pelo `create_user.py`, e não
pela interface, **um administrador nunca aparece na lista de quem pode ser
adicionado ao grupo de outro**.

Na prática, dois administradores usando a mesma instalação ficam completamente
separados: não veem os usuários um do outro, não entram nos grupos um do outro
e não têm como alcançar o conteúdo um do outro.

Se você precisa que duas pessoas administrem o mesmo conjunto de compromissos,
o caminho é as duas usarem grupos criados pelo mesmo administrador, com a
segunda entrando como usuária comum.

### Resumo

| Ação | Membro comum | Autor do conteúdo | Administrador do grupo |
|---|---|---|---|
| Ver o conteúdo do grupo | ✅ | ✅ | ✅ |
| Criar compromissos e anotações | ✅ | ✅ | ✅ |
| Editar/apagar o próprio conteúdo | ✅ | ✅ | ✅ |
| Editar/apagar conteúdo alheio | ❌ | ❌ | ✅ |
| Alterar o grupo e seus membros | ❌ | ❌ | ✅ |

---

## Isolamento entre administradores

Cada administrador enxerga apenas o próprio mundo:

- **Grupos**: só os que ele criou aparecem no painel
- **Usuários**: só os que ele mesmo cadastrou e os que já são membros de algum
  grupo dele
- Ao adicionar membros, só é possível escolher entre esses usuários

Ou seja, dois administradores usando a mesma instalação não enxergam nem
interferem nos usuários um do outro.

---

## O script `create_user.py`

É a única forma de criar administradores do sistema — de propósito, para que
essa permissão não possa ser concedida pela interface web.

```bash
# Local
python create_user.py

# No contêiner
docker compose exec web python create_user.py
```

Ele abre um menu:

```
==================================================
  GERENCIAMENTO DE USUÁRIOS
==================================================

1. Criar novo administrador
2. Listar todos os usuários
3. Alterar senha de usuário
4. Deletar usuário
5. Sair
```

### 1. Criar novo administrador

Pede nome de usuário e senha (mínimo 6 caracteres, digitada sem aparecer na
tela). Recusa nomes já existentes.

O usuário criado aqui **sempre** é administrador do sistema. Para criar
usuários comuns, use a interface web.

### 2. Listar todos os usuários

Mostra nome, tipo, data de criação e identificador de todos, com o total de
administradores e usuários comuns.

### 3. Alterar senha de usuário

Serve para qualquer usuário, administrador ou não. É o caminho para destravar
alguém que esqueceu a senha ou que estourou o limite de tentativas de login —
não existe recuperação de senha pela própria aplicação.

### 4. Deletar usuário

Apaga o usuário e, junto, **todos os compromissos e anotações dele**. Pede
confirmação digitada.

Duas situações são bloqueadas:

- **O único administrador do sistema** não pode ser apagado
- Um usuário que **administra grupos** não pode ser apagado; primeiro apague os
  grupos dele ou transfira os compromissos

---

## Criar usuários pela interface

1. Entre como administrador
2. **Administração** no topo → **+ Novo Usuário**
3. Informe nome (3 a 80 caracteres) e senha (mínimo 6), duas vezes

Usuários criados aqui são sempre comuns, nunca administradores.

Se algo estiver fora das regras, a mensagem aparece embaixo do campo
correspondente e nada é gravado.

---

## Criar e gerenciar grupos

### Criar

**Administração** → **+ Novo Grupo**. Nome de 3 a 120 caracteres e descrição
opcional de até 500.

> Nomes curtos como "TI" ou "RH" são recusados pelo mínimo de 3 caracteres.
> Use algo como "Equipe de TI".

Quem cria o grupo torna-se o administrador dele.

### Adicionar membros

Na tabela de grupos, **Gerenciar Membros** → escolha o usuário → **Adicionar**.

Dois pontos que costumam pegar:

- **Adicione você também.** Criar o grupo não coloca você dentro dele, e só
  membros enxergam o conteúdo. Enquanto você não for membro, o grupo aparece
  vazio na tela principal.
- **Um usuário pode estar em vários grupos.** Adicionar alguém a um segundo
  grupo não o remove do primeiro. A coluna **Grupos**, no painel, mostra a
  quais grupos cada pessoa pertence.

### Remover membros

Na mesma tela, **Remover** ao lado do usuário. O conteúdo que ele criou
permanece no grupo; ele apenas deixa de ter acesso.

### Editar e apagar

**Editar** permite mudar nome e descrição. Na mesma tela existe **Deletar
Grupo**, que pede confirmação.

> Apagar um grupo apaga junto **todos os compromissos e anotações** dele. Não
> há como desfazer.

---

## O painel de administração

### Gerenciar Grupos de Tarefas

Lista os grupos que **você** criou, com quantidade de membros, quantidade de
compromissos e data de criação. Cada linha tem **Gerenciar Membros** e
**Editar**.

### Gerenciar Usuários

Lista os usuários comuns sob sua gestão, com a coluna **Grupos** mostrando a
quais dos seus grupos cada um pertence, ou "Nenhum grupo" para quem ainda não
foi vinculado.

---

## Fluxo completo de configuração

Do zero até a equipe usando:

```bash
# 1. Criar o administrador (linha de comando, opção 1)
docker compose exec web python create_user.py
```

Depois, na interface web:

2. Entre com o administrador
3. **Administração** → **+ Novo Grupo** → crie o grupo
4. **+ Novo Usuário** → crie cada pessoa da equipe
5. **Gerenciar Membros** → adicione todos, **incluindo você**
6. Volte à tela principal e crie o primeiro compromisso

---

## Problemas comuns

### "Você não pertence a nenhum grupo"

Você ainda não foi adicionado como membro. Se for administrador, entre em
**Administração** → **Gerenciar Membros** e adicione-se ao grupo. Criar o grupo
não inclui você automaticamente.

### Não consigo editar o compromisso de um colega

Comportamento esperado: cada pessoa altera apenas o próprio conteúdo. Só o
administrador **daquele grupo** pode mexer no dos outros. Ser administrador do
sistema não basta.

### Um usuário sumiu da lista de usuários

O painel mostra apenas os usuários que você cadastrou ou que já pertencem a
algum grupo seu. Usuários de outro administrador não aparecem, e isso é
proposital.

### Adicionei alguém a um segundo grupo e não sei se continua no primeiro

Continua. A coluna **Grupos** no painel lista todos os grupos de cada usuário.

### O grupo não foi criado e a tela voltou sem explicação

Não deveria acontecer: os erros aparecem embaixo do campo. Se o nome tiver
menos de 3 caracteres, a mensagem estará ali.

### Esqueci a senha do administrador

Use o `create_user.py`, opção **3**. É preciso acesso ao servidor.
