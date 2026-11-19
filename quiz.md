# Quiz — AWS Systems Manager

Test yourself: 5 questions, answers hidden below. No peeking!

---

## Questions

**1.** You launch an EC2 instance in a **private subnet** with no NAT Gateway and no VPC endpoints. It never appears in Fleet Manager. What is the most likely cause, and what is the fix?

**2.** Your security team says: "No SSH keys, no bastion host, no port 22 open anywhere." Which Systems Manager capability gives engineers shell access to instances anyway, and how is each session audited?

**3.** You need to run `apt-get update && apt-get upgrade -y` on 200 web servers tagged `Role=web`, but only 3 of them report back. Name **two** things you would check first.

**4.** A database password is stored in Parameter Store as a **SecureString**. What two AWS pieces must be in place for an EC2 instance to read it — and why isn't the parameter's own encryption enough?

**5.** Your patching window runs Sunday 02:00–04:00 for instances tagged `PatchGroup=web`, but the database servers keep getting rebooted too. What tagging/baseline mistake causes this, and how do you fix it?

---

## Answers

<details>
<summary><strong>Click to reveal answers</strong></summary>

**1.** The **SSM Agent can't phone home**. It opens an *outbound* HTTPS connection (443) to the Systems Manager endpoints. With no NAT and no VPC endpoints, there is no route out. Fix: add interface VPC endpoints for `ssm`, `ssmmessages`, and `ec2messages` (production default — traffic stays inside AWS), or route through a NAT Gateway. The instance shows up in Fleet Manager within minutes.

**2.** **Session Manager.** Engineers start a session from the console or CLI (`aws ssm start-session --target i-...`); the agent's outbound connection carries the shell — no inbound port, no key. Auditing: enable logging in Session Manager preferences so every session is written to **S3 and/or CloudWatch Logs**, and every `StartSession` API call is recorded in **CloudTrail**. IAM controls who may start sessions on which (tagged) instances.

**3.** Check (a) **whether the SSM Agent is actually running and registered** on the silent instances — `describe-instance-information` shows `PingStatus`; `ConnectionLost` means agent down, wrong IAM role, or no network path to SSM endpoints; and (b) **the Run Command targets** — `send-command` with `tag:Role=web` only hits instances carrying that exact tag, and only instances the agent can see. Also check the command's timeout and each invocation's `StandardErrorContent`.

**4.** Two pieces: (1) the instance's IAM role must allow `ssm:GetParameter` (with `WithDecryption`) on that parameter ARN, and (2) it must allow `kms:Decrypt` on the **KMS key** that encrypts the SecureString. Encryption alone isn't access control — KMS holds the key, and the *key policy / IAM policy* decides who may use it. Without `kms:Decrypt`, the agent gets ciphertext it cannot open.

**5.** The DB servers are tagged `PatchGroup=web` (or share the same patch group / maintenance window target). Patch groups are just **tags** — one wrong tag enrolls a server in the wrong window. Fix: tag DB servers `PatchGroup=db`, create a separate patch baseline + maintenance window for the DB group (different day/time), and use `describe-patch-groups` to verify which instances belong to which group before patch day.

</details>
