# API Gateway: Nginx sem root (a imagem "unprivileged" já roda com o usuário nginx)
FROM nginxinc/nginx-unprivileged:1.29.1-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY web/ /usr/share/nginx/html/

EXPOSE 8000
