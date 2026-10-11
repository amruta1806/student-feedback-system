FROM nginx:alpine
COPY feedback.html /usr/share/nginx/html/index.html
EXPOSE 80
