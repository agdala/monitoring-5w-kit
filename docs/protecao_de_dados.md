# Proteção de dados no monitoramento 5W

Documento curto sobre como este projeto trata dados de pessoas e por que. Usa os princípios da
LGPD (Lei nº 13.709/2018) como referência de boas práticas. Não é parecer jurídico e não faz
afirmações sobre o regime jurídico aplicável a organismos internacionais.

## 1. Minimização: o 5W trabalha com números, não com pessoas

O relato mensal de um parceiro é uma contagem: quantas pessoas, de que sexo e faixa etária,
receberam qual serviço, em qual município e mês. Nenhum campo identifica uma pessoa. Isso
segue os princípios de **finalidade, adequação e necessidade** (art. 6º, I a III): para
acompanhar metas, a coordenação não precisa saber quem foi atendido, só quantos.

No projeto:

- os relatos (`data/sintetico/relatos.csv`) só têm contagens agregadas;
- a população sintética de pessoas existe apenas na memória do gerador, para produzir o
  gabarito. Ela **não é gravada em disco**: o que sai é o gabarito agregado por setor, UF,
  município e mês;
- todos os dados são sintéticos, inclusive nomes de parceiros (combinação de palavras fixas com
  sobrenomes do Faker, marcada como fictícia).

**Regra prática para dados reais:** se um campo não muda nenhuma decisão de coordenação, ele
não entra no formulário do 5W.

## 2. Controle de divulgação: contagem pequena também identifica

Um número agregado pode revelar uma pessoa quando é pequeno e o recorte é fino ("1 mulher de
60 anos ou mais atendida com abrigo em um município pequeno"). Por isso, toda tabela
desagregada publicada passa pelo controle de divulgação (`src/m5w/disclosure.py`):

| Etapa | Regra |
|---|---|
| Supressão primária | célula com 1 a 4 pessoas fica vazia (limiar k = 5) |
| Supressão secundária | se só uma célula do grupo foi suprimida e o total é publicado, suprime-se também a menor célula positiva, para que o valor não seja recuperado por subtração |
| Teste automático | o CI falha se qualquer célula publicada tiver de 1 a 4 pessoas |

É o mesmo critério adotado no projeto irmão
[sismigra-analytics](https://github.com/agdala/sismigra-analytics). Zero é publicado: não
identifica ninguém.

Os arquivos de trabalho interno (`reports/*.csv` sem desagregação por pessoa) servem à
coordenação; só `reports/publicacao/` é pensado para circular fora dela.

## 3. Dupla contagem: estimar sem cruzar registros

Somar os relatos conta duas vezes a pessoa atendida por dois parceiros. Os três métodos deste
projeto (soma, máximo por município, união sob independência) **estimam** as pessoas únicas a
partir dos números agregados, sem tocar em dados pessoais. São estimativas, com erro medido
contra um gabarito que só existe porque os dados são sintéticos.

**A deduplicação real exige cruzamento de registros** (record linkage) entre as bases dos
parceiros, o que significa tratar dados pessoais de terceiros. Antes disso, é preciso:

1. **acordo de compartilhamento de dados** entre as organizações, com finalidade específica,
   base legal e prazo de retenção definidos;
2. **minimização no cruzamento**: chaves pseudonimizadas (hash com sal secreto de campos como
   nome normalizado e data de nascimento), nunca o cadastro completo;
3. **segurança** (art. 46): acesso restrito, registro de quem cruzou o quê, descarte das
   chaves ao fim do processo;
4. **publicação só do agregado**: o resultado do cruzamento volta ao 5W como número, com o
   mesmo controle de divulgação.

O projeto irmão [record-linkage-kit](https://github.com/agdala/record-linkage-kit) mostra esse
cruzamento com dados sintéticos. Na prática, um cruzamento pontual numa amostra de municípios
pode calibrar o método de estimativa usado no 5W, sem cruzar tudo todo mês.

## 4. Checklist antes de publicar um produto do 5W

- [ ] O produto usa só tabelas de `reports/publicacao/` ou totais sem desagregação?
- [ ] Nenhuma célula de pessoas entre 1 e 4?
- [ ] Recortes finos (município x sexo x idade) foram evitados quando o município é pequeno?
- [ ] O texto diz qual método de pessoas únicas foi usado e qual a margem de erro conhecida?
- [ ] Nenhum nome de pessoa, documento ou contato aparece em anexos ou comentários?
