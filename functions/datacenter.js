const records = require('./datacenter-data');

exports.handler = async (event) => {
    const id = parseInt(event.queryStringParameters?.id, 10);

    if (isNaN(id)) {
        return {
            statusCode: 400,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ error: 'id parameter is required' })
        };
    }

    const record = records[id];
    if (record === undefined) {
        return {
            statusCode: 404,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ error: 'Not found' })
        };
    }

    return {
        statusCode: 200,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(record)
    };
};
