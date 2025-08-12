from flask import Blueprint, render_template

web = Blueprint("web", __name__)

@web.route("/")
def index():
    return render_template("index.html")

@web.route("/buy")
def buy():
    return render_template("buy.html")

@web.route("/support")
def support():
    return render_template("support.html")

@web.route("/test")
def test():
    return render_template("telegram_webapp_test.html")