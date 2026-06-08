.PHONY: help install migrate migrations run worker shell superuser clean install-postgres install-redis redis-start redis-stop db-shell db-create

help:
	@echo "Usage: make <command>"
	@echo ""
	@echo "Available commands:"
	@echo "  install      - Install dependencies"
	@echo "  migrate      - Apply database migrations"
	@echo "  migrations   - Create new database migrations"
	@echo "  run          - Start the Django development server"
	@echo "  worker       - Start the Celery worker"
	@echo "  shell        - Open the Django shell"
	@echo "  superuser    - Create a Django superuser"
	@echo "  install-postgres - Install PostgreSQL and development headers"
	@echo "  install-redis    - Install Redis server"
	@echo "  redis-start  - Start Redis server"
	@echo "  redis-stop   - Stop Redis server"
	@echo "  db-shell     - Access the PostgreSQL shell (psql)"
	@echo "  db-create    - Create the 'guillermo' database"
	@echo "  clean        - Remove python compiled files"

install:
	pip install -r requirements.txt

migrate:
	python manage.py migrate

migrations:
	python manage.py makemigrations

run:
	python manage.py runserver

worker:
	celery -A project worker --loglevel=info

shell:
	python manage.py shell

superuser:
	python manage.py createsuperuser

install-postgres:
	sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib libpq-dev

install-redis:
	sudo apt-get update && sudo apt-get install -y redis-server

redis-start:
	sudo systemctl start redis-server

redis-stop:
	sudo systemctl stop redis-server

db-shell:
	sudo -u postgres psql

db-create:
	sudo -u postgres createdb guillermo

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf staticfiles

refresh:
	git pull
	gotoguillermo
	python manage.py collectstatic --noinput
	python manage.py migrate
	sudo systemctl restart celery.service 
	sudo systemctl restart nginx.service 
	sudo systemctl restart gunicorn