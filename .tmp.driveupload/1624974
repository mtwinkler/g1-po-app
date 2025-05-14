# Step 1: Specify the Base Image
FROM python:3.9-slim

# Step 2: Set the Working Directory
WORKDIR /app

# Step 3: Copy Dependencies File
COPY requirements.txt .

# Step 4: Install Dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Step 5: Copy Application Code
COPY . .

# Step 6: Expose the Port
EXPOSE 8080

# Step 7: Define Environment Variable for the Port
ENV PORT=8080

# Step 8: Copy entrypoint script and make it executable
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Step 9: Set the Entrypoint
ENTRYPOINT ["/entrypoint.sh"]