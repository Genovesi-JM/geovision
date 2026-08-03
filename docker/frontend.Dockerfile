FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY . /usr/share/nginx/html
RUN rm -rf /usr/share/nginx/html/backend /usr/share/nginx/html/mobile /usr/share/nginx/html/.git
EXPOSE 80
