ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache py3-pip py3-virtualenv git g++ make python3-dev
COPY ./ /app/

RUN python3 -m venv /app/venv
RUN /app/venv/bin/pip install /app

# Copy data for add-on
RUN chmod a+x /app/run.sh

CMD [ "/app/run.sh" ]
