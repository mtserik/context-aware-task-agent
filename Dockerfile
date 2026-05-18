# Step 1: Use an official, lightweight Python runtime as a parent image
FROM python:3.11-slim

# Step 2: Set environment variables to optimize Python inside the container
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Step 3: Set the working directory inside the container
WORKDIR /app

# Step 4: Install system dependencies (needed for certain Python packages or network tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Step 5: Copy the requirements file into the container
COPY requirements.txt .

# Step 6: Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Step 7: Expose the port FastAPI will run on
EXPOSE 8000

# Step 8: Define the default command to run the application using Uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]