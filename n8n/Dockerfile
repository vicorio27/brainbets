FROM n8nio/n8n:1.44.0

USER root

# Install Python for running the prediction engine scripts inside n8n workflows
RUN apk add --no-cache python3 py3-pip

# Switch back to the default n8n user so the persisted data directory (/home/node/.n8n)
# and webhook registration work as expected.
USER node
