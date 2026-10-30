# Start from a lightweight Python image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy dependency list first (before the code) so Docker can cache this layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual application code
COPY . .

# Document which port this container listens on
EXPOSE 3000

# Version label, pased in at build time: docker build --build-arg APP_VERSION=build-7
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Command that runs when the container starts
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]


