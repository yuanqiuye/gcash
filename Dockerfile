# Use a lightweight Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies if necessary (e.g., for sqlite3 and pg_dump)
RUN apt-get update && apt-get install -y sqlite3 postgresql-client && bash -c "rm -rf /var/lib/apt/lists/*"

# Copy the project files
COPY pyproject.toml README.md ./
COPY gnucash_cli/ ./gnucash_cli/

# Install the package which automatically registers the "gcash" command
RUN pip install --no-cache-dir .

# Create a generic workspace directory for mounting files
RUN mkdir /workspace

# Set default command (can be overridden by docker run)
ENTRYPOINT ["gcash"]
CMD ["--help"]
