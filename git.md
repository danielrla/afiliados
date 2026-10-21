1. Criando e Juntando uma Nova Funcionalidade (Feature)
Sempre parta da main atualizada para criar uma nova funcionalidade.

# 1. Garanta que você está na branch principal
git checkout main

# 2. Baixe as atualizações mais recentes do GitHub (boa prática)
git pull origin main

# 3. Crie e mude para a nova branch de funcionalidade
git checkout -b feature/nome-da-funcao

# [ÁREA DE TRABALHO] Faça suas alterações no código aqui...

# 4. Adicione os arquivos alterados para o commit
git add .

# 5. Salve suas alterações com uma mensagem clara
git commit -m "Adiciona nova funcionalidade de [nome]"

# 6. Volte para a branch principal para fazer a junção
git checkout main

# 7. Junte as alterações da feature na main
git merge feature/nome-da-funcao

# 8. Envie a main atualizada para o GitHub
git push origin main

# 9. (Opcional) Apague a branch local que já foi mesclada
git branch -d feature/nome-da-funcao

2. Criando e Juntando uma Correção Urgente (Hotfix)
O processo é idêntico, mas usamos a nomenclatura hotfix/ para manter o histórico do seu projeto organizado.

# 1. Volte para a main e garanta que ela está atualizada
git checkout main
git pull origin main

# 2. Crie e mude para a branch de hotfix
git checkout -b hotfix/corrigi-bug-x

# [ÁREA DE TRABALHO] Corrija o bug no código aqui...

# 3. Adicione e commite a correção
git add .
git commit -m "Corrige bug crítico no componente X"

# 4. Volte para a branch principal
git checkout main

# 5. Junte a correção na main
git merge hotfix/corrigi-bug-x

# 6. Envie para o GitHub
git push origin main

# 7. (Opcional) Apague a branch de hotfix local
git branch -d hotfix/corrigi-bug-x

