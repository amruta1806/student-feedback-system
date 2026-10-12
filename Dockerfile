FROM nginx:alpine
COPY feedback.html /usr/share/nginx/html/index.html
COPY results.html /usr/share/nginx/html/results.html
EXPOSE 80
