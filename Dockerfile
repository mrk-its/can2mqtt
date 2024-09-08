ARG BUILD_FROM
FROM $BUILD_FROM as builder

RUN apk add --no-cache py3-pip git g++ make python3-dev
COPY ./ /app/

RUN pip install --user /app

FROM $BUILD_FROM
RUN apk add python3
COPY --from=builder /root/.local /root/.local
COPY ./run.sh /app/run.sh

# Copy data for add-on
RUN chmod a+x /app/run.sh
RUN find /root/.local/
ENV PATH="/root/.local/bin:$PATH"
CMD [ "/app/run.sh" ]
