#!/usr/bin/env python3

from flask import Flask, request, jsonify

app = Flask('exact simulator')

@app.route('/oath2/auth')
def authenticate():
    pass


@app.route('/oath2/token')
def updateToken():
    pass


@app.route('/v1/<division>/financialtransaction/TransactionLines')
def getTransactions(division):
    return open('transactions.json').read()


@app.route('/v1/<division>/crm/Accounts')
def getAccounts(division):
    return open('users.json').read()


@app.route('/v1/<division>/financial/GLAccounts')
def getGLAccounts(division):
    pass


@app.route('/v1/<division>/financial/VATs')
def getBtws(division):
    pass


if __name__ == '__main__':
    app.run(port=8001)
