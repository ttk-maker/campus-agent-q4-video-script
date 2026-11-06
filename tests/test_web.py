import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from src.web import Application,make_server
from src.scenarios import scenario

class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=Application(Path(self.temp.name)/"web.db");self.server=make_server(self.app,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
        self.base=f"http://127.0.0.1:{self.server.server_port}"
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def call(self,path,body=None,headers=None):
        h={"Content-Type":"application/json","X-CSRF-Token":self.app.token};h.update(headers or {})
        req=urllib.request.Request(self.base+path,data=None if body is None else (body if isinstance(body,bytes) else json.dumps(body).encode()),headers=h)
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.read()
        except urllib.error.HTTPError as e:return e.code,e.read()
    def job(self,payload,path="/api/jobs"):
        status,raw=self.call(path,payload);self.assertEqual(status,202);key=json.loads(raw)["job_id"]
        for _ in range(300):
            status,raw=self.call("/api/jobs/"+key);j=json.loads(raw)
            if j["state"]!="running":return j
            time.sleep(.01)
        self.fail("job timeout")
    def test_pages_health_and_manual(self):
        for path in ("/","/manual.html","/app.js","/style.css","/api/health","/api/bootstrap"):
            self.assertEqual(self.call(path)[0],200)
    def test_normal_and_repeat(self):
        p=scenario("normal");self.job(p);j=self.job(p)
        self.assertEqual(j["result"]["steps_used"],0);self.assertEqual(j["result"]["status"],"completed")
    def test_edit_preserves_unsupported_text_and_fails(self):
        first=self.job(scenario("normal"));script=first["result"]["script"]
        script["scenes"][0]["voiceover"]="效率提升80%"
        j=self.job({"job_id":first["job_id"],"script":script},"/api/review")
        self.assertEqual(j["result"]["mode"],"review");self.assertEqual(j["result"]["status"],"cannot_satisfy")
        self.assertEqual(j["result"]["script"]["scenes"][0]["voiceover"],"效率提升80%")
    def test_edit_duration_rechecked_then_agent_repairs(self):
        first=self.job(scenario("normal"));script=first["result"]["script"]
        script["scenes"][0]["seconds"]=50
        review=self.job({"job_id":first["job_id"],"script":script},"/api/review")
        self.assertEqual(review["result"]["estimated_total_seconds"],68)
        self.assertEqual(review["result"]["script_status"],"unverified")
        p=review["payload"];p["max_steps"]=16;fixed=self.job(p)
        self.assertEqual(fixed["result"]["status"],"completed")
    def test_valid_edit_uses_fresh_request(self):
        first=self.job(scenario("normal"));j=self.job({"job_id":first["job_id"],"script":first["result"]["script"]},"/api/review")
        self.assertNotEqual(j["payload"]["request"]["request_id"],first["payload"]["request"]["request_id"])
        self.assertEqual(j["result"]["status"],"completed")
    def test_no_materials_and_missing(self):
        for name in ("no_materials","missing"):
            self.assertEqual(self.job(scenario(name))["result"]["status"],"needs_information")
    def test_bad_json_and_unknown_fields(self):
        for body in (b'{',b'{"x":NaN}',dict(scenario("normal"),publish=True)):
            self.assertEqual(self.call("/api/jobs",body)[0],400)
    def test_cross_origin_token_and_host(self):
        p=scenario("normal")
        self.assertEqual(self.call("/api/jobs",p,{"Origin":"http://evil.example"})[0],403)
        self.assertEqual(self.call("/api/jobs",p,{"X-CSRF-Token":"bad"})[0],403)
        self.assertEqual(self.call("/api/bootstrap",headers={"Host":"evil.example"})[0],403)
    def test_missing_job_and_api_prefix(self):
        self.assertEqual(self.call("/api/jobs/missing")[0],404);self.assertEqual(self.call("/v1")[0],404)
    def test_changed_input_rejects_reuse(self):
        p=scenario("normal");self.job(p);p["request"]["target_seconds"]=20
        j=self.job(p);self.assertEqual(j["state"],"error");self.assertIn("idempotency_conflict",j["error"])
    def test_malformed_edit(self):
        self.assertEqual(self.call("/api/review",{"job_id":"unknown","script":{}})[0],400)
    def test_restart_reuses_saved_result(self):
        p=scenario("normal");self.job(p);app=Application(self.app.store.path)
        job_id=app.start(p)["job_id"]
        for _ in range(300):
            j=app.job(job_id)
            if j["state"]!="running":break
            time.sleep(.01)
        self.assertEqual(j["result"]["steps_used"],0)
