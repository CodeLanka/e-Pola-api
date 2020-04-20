import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from firebase_admin import auth, credentials, firestore, initialize_app
import functools
import requests


app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})
cred = credentials.Certificate("./serviceAccount.json")
default_app = initialize_app(cred)

db = firestore.client()
needs_ref = db.collection("needs")
product_ref = db.collection("products")


def authenticate():
    message = {"message": "Authenticate."}
    resp = jsonify(message)
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = 'Basic realm="My Realm"'
    return resp


def requires_authorization(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        id_token = request.headers["Authorization"].split("=").pop()
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token["uid"]
        if not uid:
            return authenticate()
        return f(*args, **kwargs)

    return decorated


def filter_from_all(column, filter):
    return {
        doc.id: doc.to_dict() for doc in needs_ref.where(column, "in", filter).stream()
    }


def query_from_fb(columns, values):
    mappings = list(zip(columns, values))
    mappings = [t for t in mappings if t[1]]
    result = []

    main_query = None
    cat_query = None
    prod_query = None
    prod_done = False

    for mapping in mappings:
        if (
            mapping[0] == columns[0]
            or mapping[0] == columns[1]
            or mapping[0] == columns[2]
        ):
            if main_query is None:
                main_query = needs_ref.where(mapping[0], "==", mapping[1])
            else:
                if len(mapping[1].split(",")) > 1:
                    main_query = main_query.where(
                        mapping[0], "in", list(map(str.strip, mapping[1].split(",")))
                    )
                else:
                    main_query = main_query.where(mapping[0], "==", mapping[1])
        elif mapping[0] == columns[3]:
            prod_query = product_ref.where(
                mapping[0], "in", list(map(str.strip, mapping[1].split(",")))
            )
    # THIS WHOLE LOGIC NEEDS TO BE RE WRITTEN AND SIMPLIFIED WITH THE SIMPLIFIED DB STRUCTURE.
    if main_query:
        area_data = {doc.id: doc.to_dict() for doc in main_query.stream()}
        result = area_data
    if cat_query:
        cat_data = {doc.id: doc.to_dict() for doc in cat_query.stream()}
        cat_list = list(set([l["category"] for l in list(cat_data.values())]))
        if prod_query and main_query:
            prod_done = True
            prod_data = {doc.id: doc.to_dict() for doc in prod_query.stream()}
            prod_list = {
                id: data
                for id, data in prod_data.items()
                if data["category"] in cat_list
            }
            result = list(prod_list.values())
            if main_query:
                result = {
                    id: data
                    for id, data in area_data.items()
                    if data["products_id"] in list(prod_list.keys())
                }
            else:
                result = {}
        elif not prod_query and main_query:
            result = {
                id: data
                for id, data in area_data.items()
                if data["category"]
                in cat_list  # ToDo: There's a bug here: need to fetch the category by querying the product_id in products table.
            }
        else:
            result = {}
    if prod_query and not prod_done:
        if main_query:
            prod_list = list(map(str.strip, mappings[-1][1].split(",")))
            result = {
                id: data
                for id, data in area_data.items()
                if data["products_id"] in prod_list
            }
        else:
            result = filter_from_all(mappings[-1][0], prod_list)

    return result

def merge_id(id, obj):
  obj.update(id=id)
  return obj

@app.route("/api/v2/needs/status", methods=["POST"])
def put_needs():
    needs = request.get_json()['needs']
    to = "" if "to" not in request.args else request.args['to']
    print(needs,to)
    collection = db.collection("needs")
    batch = db.batch()
    for need in needs:
       ref = collection.document(need)
       batch.update(ref, {u'status': to})
    query = batch.commit()
    #print(query)
    return "OK", 200


@app.route("/api/v2/needs", methods=["GET"])
def get_needs():
    products = [] if not request.args else request.args['products'].split(",")
    area = "" if "area" not in request.args else request.args['area']
    query = db.collection("needs")
    if( len(products) > 0 ):
        query =  query.where("products_id", "in", products)
    if(area != ""):
       query =  query.where("location.area", "==", area)
    needs = query.stream()
    #print(jsonify(response(needs)))
    return jsonify([merge_id(doc.id, doc.to_dict()) for doc in needs]), 200

@app.route("/api/v1/needs", methods=["GET"])
# @requires_authorization
def get_needs_by_location():
    try:
        args = ("area", "suburb", "category", "product")
        fb_doc_cols = ("location.area", "location.suburb", "category", "products_id")
        values = list(map(request.args.get, args))
        if any(values):
            return jsonify(query_from_fb(fb_doc_cols, values)), 200
        else:
            all_needs = {merge_id(doc.id, doc.to_dict()) for doc in needs_ref.stream()}
            return jsonify(all_needs), 200
    except Exception as e:
        return f"An Error Occured: {e}"


@app.route("/ping", methods=["GET"])
def ping():
    return "pong"


port = int(os.environ.get("PORT", 5000))
if __name__ == "__main__":
    app.run(threaded=True, host="0.0.0.0", port=port, debug=True)
