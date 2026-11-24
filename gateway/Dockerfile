# API Gateway: Nginx sem root (a imagem "unprivileged" já roda com o usuário nginx)
FROM nginxinc/nginx-unprivileged:1.31.7-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY web/ /usr/share/nginx/html/

EXPOSE 8000
