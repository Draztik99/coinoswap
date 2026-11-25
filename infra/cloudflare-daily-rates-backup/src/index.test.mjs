import test from "node:test";
import assert from "node:assert/strict";
import { isExpectedTrigger, runScheduledBackup, GITHUB_WORKFLOW_DISPATCH } from "./index.mjs";

const utc = (hh, mm) => Date.parse(`2026-11-26T${String(hh).padStart(2,"0")}:${String(mm).padStart(2,"0")}:00Z`);

test("backup triggers exactly 9 and 4 minutes before seven candidate slots", () => {
  const expected = [21,26,51,56];
  for (const hour of [9,10,11]) {
    for (let minute=0;minute<60;minute++) {
      assert.equal(isExpectedTrigger(utc(hour,minute)),expected.includes(minute));
    }
  }
  for (let minute=0;minute<60;minute++) {
    assert.equal(isExpectedTrigger(utc(12,minute)),[21,26].includes(minute));
  }
  for (const hour of [0,8,13,20,23]) {
    assert.equal(isExpectedTrigger(utc(hour,21)),false);
  }
  assert.equal(isExpectedTrigger(NaN),false);
});

test("authorized cron sends ONLY GitHub Actions backup dispatch (no Meta POST)",async () => {
  const calls = [];
  const env = { GITHUB_ACTIONS_TOKEN: "FAKE_TEST_TOKEN_NOT_REAL" };
  const result = await runScheduledBackup({scheduledTime:utc(10,51)},env,
      async (url,options) => { calls.push({url,options});return {status:204}; });
  assert.deepEqual(result,{status:"DISPATCH_ACCEPTED_NOT_PUBLISHED"});
  assert.equal(calls.length,1);
  const {url,options}=calls[0];
  assert.equal(url,GITHUB_WORKFLOW_DISPATCH);
  assert.equal(options.method,"POST");
  assert.deepEqual(JSON.parse(options.body),
    {ref:"main",inputs:{emergency:"false",backup_trigger:"true"}});
  assert.equal(options.headers.Authorization,"Bearer FAKE_TEST_TOKEN_NOT_REAL");
  assert.ok(!url.includes("facebook.com"));
  assert.ok(!url.includes("metricool.com"));
  assert.ok(!options.body.includes("FAKE_TEST_TOKEN_NOT_REAL"));
});

test("no secrets or wrong time: never call GitHub",async () => {
  let calls=0;
  const request=async()=>{calls++;return {status:204};};
  const result=await runScheduledBackup({scheduledTime:utc(14,21)}, {},request);
  assert.equal(result.status,"SKIPPED_UNEXPECTED_TIME");
  await assert.rejects(()=>runScheduledBackup({scheduledTime:utc(9,21)}, {},request),/not configured/);
  await assert.rejects(()=>runScheduledBackup({scheduledTime:utc(9,21)},
      {GITHUB_ACTIONS_TOKEN:"BAD TOKEN"},request),/not configured/);
  assert.equal(calls,0);
});

test("non-204 status and network errors fail without claiming publication",async () => {
  const env={GITHUB_ACTIONS_TOKEN:"FAKE_TEST_TOKEN_NOT_REAL"};
  await assert.rejects(()=>runScheduledBackup({scheduledTime:utc(12,21)},env,
    async()=>({status:401})),/HTTP 401/);
  await assert.rejects(()=>runScheduledBackup({scheduledTime:utc(12,21)},env,
    async()=>{throw new Error("private response");}),/request unavailable/);
});
