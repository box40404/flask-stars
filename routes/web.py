from quart import Blueprint, render_template

web = Blueprint("web", __name__)

@web.route("/")
async def index():
    return await render_template("index.html")

@web.route("/support")
async def support():
    return await render_template("support.html")

# @web.route("/test")
# async def test():
#     return await render_template("telegram_webapp_test.html")