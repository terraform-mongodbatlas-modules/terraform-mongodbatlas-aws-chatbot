# Security and IAM

This guide covers the permissions you need to deploy the module and the roles the module creates for the running app. It separates the deployer identity from the runtime identity, so you can scope each one to what it actually does.

## Deployer permissions

To run the example, the AWS identity that runs `terraform apply` needs permission to create and delete the resources the module manages: VPC and networking resources, ECR, CodeBuild, ECS, the Application Load Balancer, CloudFront, WAF, Secrets Manager, S3, IAM roles and policies, and KMS when `features.atlas_byok` is set.

The following combined policy is a placeholder that shows the shape, not a policy you can attach. As written it grants unrestricted administrator access, so do not paste or attach it. Replace the statement with the least-privilege actions you capture for your account before you create an IAM user for the demo. For a Terraform-managed deployer role, split the policy per service and attach it to the role.

<!-- TODO: replace the placeholder statement with the least-privilege policy you capture
     for your account. Record the actions from a create, update, and delete cycle, then
     scope each action to the resources the module manages. -->

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Placeholder",
      "Effect": "Allow",
      "Action": "*",
      "Resource": "*"
    }
  ]
}
```

## Atlas credential

The module creates the Atlas project, so the credential it uses needs access to your Atlas organization rather than to a single project. Use an Organization Owner, or a Service Account with the Organization Project Creator role. See [Grant Programmatic Access to an Organization](https://www.mongodb.com/docs/atlas/configure-api-access/#grant-programmatic-access-to-an-organization) in the Atlas documentation for the setup steps.

The credential is read from the standard `mongodbatlas` provider authentication environment variables or from your provider configuration. The module reads the organization ID from the credential, so there is no `atlas_org_id` input.

## Roles the module creates

The module creates runtime identities that are separate from the deployer identity. Granting deployer permissions does not grant the running app any of them.

- **ECS task role:** the app's runtime identity. It calls `bedrock-runtime` (with the Converse policy) when Bedrock is the provider, and it authenticates to Atlas as an IAM database user through `MONGODB-AWS`.
- **ECS task execution role:** pulls the image from ECR, writes logs, and reads the app secret from Secrets Manager.
- **CodeBuild role:** reads the app source from S3, writes logs, and pushes the built image to ECR.
- **Atlas IAM database user:** one per app, keyed to the task role ARN, with a role scoped to the app's database and collection.

## Network posture

The app runs in private subnets with no public IP. CloudFront reaches the internal Application Load Balancer through a VPC origin, so only the module's distribution can reach the ALB. The app reaches Atlas over PrivateLink and reaches AWS APIs over interface VPC endpoints, or over NAT when `features.vpc_endpoints` is false. Set `features.internet_egress` only when a keyed LLM provider needs the public internet.
