# Deployer permissions

The [Security and IAM](security-and-iam.md) guide separates the deployer identity from the runtime roles the module creates. This guide gives the deployer identity a least-privilege policy built from the actions the module actually calls.

Two bundles follow. The minimal example bundle covers the [minimal example](../examples/minimal). The full bundle covers every feature. Both are parameterized by two values:

- **`{aws_account_id}`**: your AWS account ID.
- **`{resource_prefix}`**: the prefix for every resource name the module creates. It defaults to `app_name`.

Replace both before you attach a policy. The `Example` tag value is fixed by the module, so the tag conditions need no edit.

## Why tag conditions

The module tags every resource it creates with two built-in tags: `Example = atlas-aws-chatbot` and `Name = <resource_prefix>`. The policy keys on `Example`, which is fixed, so the conditions are portable across accounts and deployments. A condition on `Name` would need an edit per deployment.

AWS authorizes each call against either the tags in the request or the tags on an existing resource:

- **Create** calls carry `aws:RequestTag/Example = atlas-aws-chatbot`. The module sends the tag in the create request, so the create succeeds only for the module's own resources.
- **Manage and delete** calls carry `aws:ResourceTag/Example = atlas-aws-chatbot`. The resource already exists and is tagged, so the call succeeds only against a resource the module created.
- **Read** calls stay on `Resource: "*"` with no condition. Most read APIs have no resource-level support, so a condition cannot narrow them.

A small set of actions cannot use either condition, because AWS authorizes them against a parent resource or an untaggable one. They stay on `"*"` with no condition. See [Exceptions](#exceptions).

## Minimal example policy

This is the policy for the [minimal example](../examples/minimal): WAF, interface VPC endpoints, and the deployment-ready check on, and BYOK, internet egress, log and backup export, and debug access off. It drops the whole KMS service and the NAT and EIP EC2 actions from the full bundle. Every other statement is shared.

The policy requires the boundary. Set `overrides.permissions_boundary` as shown in [Close the IAM escalation](#close-the-iam-escalation), or the deployer's `iam:CreateRole` condition denies the role creates.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudFrontCreate1",
      "Effect": "Allow",
      "Action": ["cloudfront:TagResource"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "CloudFrontManage2",
      "Effect": "Allow",
      "Action": [
        "cloudfront:DeleteDistribution",
        "cloudfront:DeleteVpcOrigin",
        "cloudfront:UpdateDistribution"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "CloudFrontRead3",
      "Effect": "Allow",
      "Action": [
        "cloudfront:CreateDistribution",
        "cloudfront:CreateVpcOrigin",
        "cloudfront:GetCachePolicy",
        "cloudfront:GetDistribution",
        "cloudfront:GetOriginRequestPolicy",
        "cloudfront:GetVpcOrigin",
        "cloudfront:ListCachePolicies",
        "cloudfront:ListOriginRequestPolicies",
        "cloudfront:ListTagsForResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CodebuildCreate1",
      "Effect": "Allow",
      "Action": ["codebuild:CreateProject"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "CodebuildManage2",
      "Effect": "Allow",
      "Action": ["codebuild:DeleteProject", "codebuild:StartBuild"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "CodebuildRead3",
      "Effect": "Allow",
      "Action": ["codebuild:BatchGetBuilds", "codebuild:BatchGetProjects"],
      "Resource": "*"
    },
    {
      "Sid": "Ec2Create1",
      "Effect": "Allow",
      "Action": [
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:CreateInternetGateway",
        "ec2:CreateRouteTable",
        "ec2:CreateSecurityGroup",
        "ec2:CreateSubnet",
        "ec2:CreateTags",
        "ec2:CreateVpc",
        "ec2:CreateVpcEndpoint"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "Ec2Manage2",
      "Effect": "Allow",
      "Action": [
        "ec2:AssociateRouteTable",
        "ec2:AttachInternetGateway",
        "ec2:CreateRoute",
        "ec2:DeleteInternetGateway",
        "ec2:DeleteRoute",
        "ec2:DeleteRouteTable",
        "ec2:DeleteSecurityGroup",
        "ec2:DeleteSubnet",
        "ec2:DeleteVpc",
        "ec2:DeleteVpcEndpoints",
        "ec2:DescribeVpcAttribute",
        "ec2:DetachInternetGateway",
        "ec2:ModifyVpcAttribute",
        "ec2:RevokeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupIngress"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "Ec2Read3",
      "Effect": "Allow",
      "Action": [
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:CreateRouteTable",
        "ec2:CreateSecurityGroup",
        "ec2:CreateSubnet",
        "ec2:CreateVpc",
        "ec2:CreateVpcEndpoint",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeInternetGateways",
        "ec2:DescribeManagedPrefixLists",
        "ec2:DescribeNetworkAcls",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribePrefixLists",
        "ec2:DescribeRouteTables",
        "ec2:DescribeSecurityGroupRules",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeVpcEndpoints",
        "ec2:DescribeVpcs",
        "ec2:DisassociateRouteTable",
        "ec2:GetManagedPrefixListEntries"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EcrCreate1",
      "Effect": "Allow",
      "Action": ["ecr:CreateRepository", "ecr:TagResource"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "EcrManage2",
      "Effect": "Allow",
      "Action": [
        "ecr:DeleteLifecyclePolicy",
        "ecr:DeleteRepository",
        "ecr:DescribeImages",
        "ecr:DescribeRepositories",
        "ecr:GetLifecyclePolicy",
        "ecr:ListTagsForResource",
        "ecr:PutLifecyclePolicy"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "EcsCreate1",
      "Effect": "Allow",
      "Action": [
        "ecs:CreateCluster",
        "ecs:CreateService",
        "ecs:RegisterTaskDefinition"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "EcsManage2",
      "Effect": "Allow",
      "Action": [
        "ecs:DeleteCluster",
        "ecs:DeleteService",
        "ecs:DescribeClusters",
        "ecs:DescribeServiceDeployments",
        "ecs:DescribeServices",
        "ecs:ListServiceDeployments",
        "ecs:UpdateService"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "EcsRead3",
      "Effect": "Allow",
      "Action": [
        "ecs:DeregisterTaskDefinition",
        "ecs:DescribeTaskDefinition",
        "ecs:TagResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ElbCreate1",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:AddTags",
        "elasticloadbalancing:CreateListener",
        "elasticloadbalancing:CreateLoadBalancer",
        "elasticloadbalancing:CreateRule",
        "elasticloadbalancing:CreateTargetGroup"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "ElbManage2",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:DeleteListener",
        "elasticloadbalancing:DeleteLoadBalancer",
        "elasticloadbalancing:DeleteRule",
        "elasticloadbalancing:DeleteTargetGroup",
        "elasticloadbalancing:ModifyLoadBalancerAttributes",
        "elasticloadbalancing:ModifyTargetGroupAttributes"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "ElbRead3",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:DescribeCapacityReservation",
        "elasticloadbalancing:DescribeListenerAttributes",
        "elasticloadbalancing:DescribeListeners",
        "elasticloadbalancing:DescribeLoadBalancerAttributes",
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeRules",
        "elasticloadbalancing:DescribeTags",
        "elasticloadbalancing:DescribeTargetGroupAttributes",
        "elasticloadbalancing:DescribeTargetGroups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IamRoleCreateWithBoundary",
      "Effect": "Allow",
      "Action": ["iam:CreateRole", "iam:PutRolePermissionsBoundary"],
      "Resource": [
        "arn:aws:iam::{aws_account_id}:role/{resource_prefix}-*",
        "arn:aws:iam::{aws_account_id}:role/mongodb-atlas-*"
      ],
      "Condition": {
        "StringEquals": {
          "iam:PermissionsBoundary": "arn:aws:iam::{aws_account_id}:policy/{resource_prefix}-permissions-boundary"
        }
      }
    },
    {
      "Sid": "IamRoleCreateWrite",
      "Effect": "Allow",
      "Action": [
        "iam:DeleteRole",
        "iam:DeleteRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:TagRole",
        "iam:UpdateAssumeRolePolicy"
      ],
      "Resource": [
        "arn:aws:iam::{aws_account_id}:role/{resource_prefix}-*",
        "arn:aws:iam::{aws_account_id}:role/mongodb-atlas-*"
      ]
    },
    {
      "Sid": "IamRoleAttachAllowlisted",
      "Effect": "Allow",
      "Action": ["iam:AttachRolePolicy"],
      "Resource": [
        "arn:aws:iam::{aws_account_id}:role/{resource_prefix}-*",
        "arn:aws:iam::{aws_account_id}:role/mongodb-atlas-*"
      ],
      "Condition": {
        "StringLike": {
          "iam:PolicyARN": [
            "arn:aws:iam::{aws_account_id}:policy/{resource_prefix}-*",
            "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
          ]
        }
      }
    },
    {
      "Sid": "IamRoleReadPass",
      "Effect": "Allow",
      "Action": [
        "iam:GetRole",
        "iam:GetRolePolicy",
        "iam:ListAttachedRolePolicies",
        "iam:ListInstanceProfilesForRole",
        "iam:ListRolePolicies",
        "iam:PassRole"
      ],
      "Resource": [
        "arn:aws:iam::{aws_account_id}:role/{resource_prefix}-*",
        "arn:aws:iam::{aws_account_id}:role/mongodb-atlas-*"
      ]
    },
    {
      "Sid": "LogsCreate1",
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "LogsRead2",
      "Effect": "Allow",
      "Action": [
        "logs:DeleteLogGroup",
        "logs:DescribeLogGroups",
        "logs:ListTagsForResource",
        "logs:PutRetentionPolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Route53Read1",
      "Effect": "Allow",
      "Action": ["route53:AssociateVPCWithHostedZone"],
      "Resource": "*"
    },
    {
      "Sid": "S3Read1",
      "Effect": "Allow",
      "Action": [
        "s3:AbortMultipartUpload",
        "s3:CreateBucket",
        "s3:DeleteBucket",
        "s3:DeleteObject",
        "s3:DeleteObjectVersion",
        "s3:GetAccelerateConfiguration",
        "s3:GetBucketAcl",
        "s3:GetBucketCORS",
        "s3:GetBucketLogging",
        "s3:GetBucketObjectLockConfiguration",
        "s3:GetBucketPolicy",
        "s3:GetBucketPublicAccessBlock",
        "s3:GetBucketRequestPayment",
        "s3:GetBucketTagging",
        "s3:GetBucketVersioning",
        "s3:GetBucketWebsite",
        "s3:GetEncryptionConfiguration",
        "s3:GetLifecycleConfiguration",
        "s3:GetObject",
        "s3:GetObjectTagging",
        "s3:GetObjectVersion",
        "s3:GetReplicationConfiguration",
        "s3:ListBucket",
        "s3:ListBucketVersions",
        "s3:ListTagsForResource",
        "s3:PutBucketPublicAccessBlock",
        "s3:PutBucketTagging",
        "s3:PutBucketVersioning",
        "s3:PutEncryptionConfiguration",
        "s3:PutLifecycleConfiguration",
        "s3:PutObject",
        "s3:PutObjectTagging"
      ],
      "Resource": [
        "arn:aws:s3:::{resource_prefix}-*",
        "arn:aws:s3:::{resource_prefix}-*/*"
      ]
    },
    {
      "Sid": "SecretsManagerCreate1",
      "Effect": "Allow",
      "Action": ["secretsmanager:CreateSecret", "secretsmanager:TagResource"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "SecretsManagerManage2",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:DeleteSecret",
        "secretsmanager:DescribeSecret",
        "secretsmanager:GetResourcePolicy",
        "secretsmanager:GetSecretValue",
        "secretsmanager:PutSecretValue"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "StsRead1",
      "Effect": "Allow",
      "Action": ["sts:GetCallerIdentity"],
      "Resource": "*"
    },
    {
      "Sid": "WafCreate1",
      "Effect": "Allow",
      "Action": ["wafv2:TagResource"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "WafManage2",
      "Effect": "Allow",
      "Action": [
        "wafv2:DeleteWebACL",
        "wafv2:GetWebACL",
        "wafv2:ListTagsForResource"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "WafRead3",
      "Effect": "Allow",
      "Action": ["wafv2:CreateWebACL"],
      "Resource": "*"
    }
  ]
}
```

## Full feature set policy

This is the policy for a deployment with every feature on: WAF, interface VPC endpoints, NAT egress, BYOK, log and backup export, and debug access. It adds the KMS service and the NAT and EIP EC2 actions to the minimal bundle.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudFrontCreate1",
      "Effect": "Allow",
      "Action": ["cloudfront:TagResource"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "CloudFrontManage2",
      "Effect": "Allow",
      "Action": [
        "cloudfront:DeleteDistribution",
        "cloudfront:DeleteVpcOrigin",
        "cloudfront:UpdateDistribution"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "CloudFrontRead3",
      "Effect": "Allow",
      "Action": [
        "cloudfront:CreateDistribution",
        "cloudfront:CreateVpcOrigin",
        "cloudfront:GetCachePolicy",
        "cloudfront:GetDistribution",
        "cloudfront:GetOriginRequestPolicy",
        "cloudfront:GetVpcOrigin",
        "cloudfront:ListCachePolicies",
        "cloudfront:ListOriginRequestPolicies",
        "cloudfront:ListTagsForResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CodebuildCreate1",
      "Effect": "Allow",
      "Action": ["codebuild:CreateProject"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "CodebuildManage2",
      "Effect": "Allow",
      "Action": ["codebuild:DeleteProject", "codebuild:StartBuild"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "CodebuildRead3",
      "Effect": "Allow",
      "Action": ["codebuild:BatchGetBuilds", "codebuild:BatchGetProjects"],
      "Resource": "*"
    },
    {
      "Sid": "Ec2Create1",
      "Effect": "Allow",
      "Action": [
        "ec2:AllocateAddress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:CreateInternetGateway",
        "ec2:CreateNatGateway",
        "ec2:CreateRouteTable",
        "ec2:CreateSecurityGroup",
        "ec2:CreateSubnet",
        "ec2:CreateTags",
        "ec2:CreateVpc",
        "ec2:CreateVpcEndpoint"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "Ec2Manage2",
      "Effect": "Allow",
      "Action": [
        "ec2:AssociateRouteTable",
        "ec2:AttachInternetGateway",
        "ec2:CreateRoute",
        "ec2:DeleteInternetGateway",
        "ec2:DeleteNatGateway",
        "ec2:DeleteRoute",
        "ec2:DeleteRouteTable",
        "ec2:DeleteSecurityGroup",
        "ec2:DeleteSubnet",
        "ec2:DeleteVpc",
        "ec2:DeleteVpcEndpoints",
        "ec2:DescribeVpcAttribute",
        "ec2:DetachInternetGateway",
        "ec2:ModifyVpcAttribute",
        "ec2:ReleaseAddress",
        "ec2:RevokeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupIngress"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "Ec2Read3",
      "Effect": "Allow",
      "Action": [
        "ec2:AllocateAddress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:CreateNatGateway",
        "ec2:CreateRouteTable",
        "ec2:CreateSecurityGroup",
        "ec2:CreateSubnet",
        "ec2:CreateVpc",
        "ec2:CreateVpcEndpoint",
        "ec2:DescribeAddresses",
        "ec2:DescribeAddressesAttribute",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeInternetGateways",
        "ec2:DescribeManagedPrefixLists",
        "ec2:DescribeNatGateways",
        "ec2:DescribeNetworkAcls",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribePrefixLists",
        "ec2:DescribeRouteTables",
        "ec2:DescribeSecurityGroupRules",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeVpcEndpoints",
        "ec2:DescribeVpcs",
        "ec2:DisassociateAddress",
        "ec2:DisassociateRouteTable",
        "ec2:GetManagedPrefixListEntries"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EcrCreate1",
      "Effect": "Allow",
      "Action": ["ecr:CreateRepository", "ecr:TagResource"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "EcrManage2",
      "Effect": "Allow",
      "Action": [
        "ecr:DeleteLifecyclePolicy",
        "ecr:DeleteRepository",
        "ecr:DescribeImages",
        "ecr:DescribeRepositories",
        "ecr:GetLifecyclePolicy",
        "ecr:ListTagsForResource",
        "ecr:PutLifecyclePolicy"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "EcsCreate1",
      "Effect": "Allow",
      "Action": [
        "ecs:CreateCluster",
        "ecs:CreateService",
        "ecs:RegisterTaskDefinition"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "EcsManage2",
      "Effect": "Allow",
      "Action": [
        "ecs:DeleteCluster",
        "ecs:DeleteService",
        "ecs:DescribeClusters",
        "ecs:DescribeServiceDeployments",
        "ecs:DescribeServices",
        "ecs:ListServiceDeployments",
        "ecs:UpdateService"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "EcsRead3",
      "Effect": "Allow",
      "Action": [
        "ecs:DeregisterTaskDefinition",
        "ecs:DescribeTaskDefinition",
        "ecs:TagResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ElbCreate1",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:AddTags",
        "elasticloadbalancing:CreateListener",
        "elasticloadbalancing:CreateLoadBalancer",
        "elasticloadbalancing:CreateRule",
        "elasticloadbalancing:CreateTargetGroup"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "ElbManage2",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:DeleteListener",
        "elasticloadbalancing:DeleteLoadBalancer",
        "elasticloadbalancing:DeleteRule",
        "elasticloadbalancing:DeleteTargetGroup",
        "elasticloadbalancing:ModifyLoadBalancerAttributes",
        "elasticloadbalancing:ModifyTargetGroupAttributes"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "ElbRead3",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:DescribeCapacityReservation",
        "elasticloadbalancing:DescribeListenerAttributes",
        "elasticloadbalancing:DescribeListeners",
        "elasticloadbalancing:DescribeLoadBalancerAttributes",
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeRules",
        "elasticloadbalancing:DescribeTags",
        "elasticloadbalancing:DescribeTargetGroupAttributes",
        "elasticloadbalancing:DescribeTargetGroups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IamRoleCreateWithBoundary",
      "Effect": "Allow",
      "Action": ["iam:CreateRole", "iam:PutRolePermissionsBoundary"],
      "Resource": [
        "arn:aws:iam::{aws_account_id}:role/{resource_prefix}-*",
        "arn:aws:iam::{aws_account_id}:role/mongodb-atlas-*"
      ],
      "Condition": {
        "StringEquals": {
          "iam:PermissionsBoundary": "arn:aws:iam::{aws_account_id}:policy/{resource_prefix}-permissions-boundary"
        }
      }
    },
    {
      "Sid": "IamRoleCreateWrite",
      "Effect": "Allow",
      "Action": [
        "iam:DeleteRole",
        "iam:DeleteRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:TagRole",
        "iam:UpdateAssumeRolePolicy"
      ],
      "Resource": [
        "arn:aws:iam::{aws_account_id}:role/{resource_prefix}-*",
        "arn:aws:iam::{aws_account_id}:role/mongodb-atlas-*"
      ]
    },
    {
      "Sid": "IamRoleAttachAllowlisted",
      "Effect": "Allow",
      "Action": ["iam:AttachRolePolicy"],
      "Resource": [
        "arn:aws:iam::{aws_account_id}:role/{resource_prefix}-*",
        "arn:aws:iam::{aws_account_id}:role/mongodb-atlas-*"
      ],
      "Condition": {
        "StringLike": {
          "iam:PolicyARN": [
            "arn:aws:iam::{aws_account_id}:policy/{resource_prefix}-*",
            "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
          ]
        }
      }
    },
    {
      "Sid": "IamRoleReadPass",
      "Effect": "Allow",
      "Action": [
        "iam:GetRole",
        "iam:GetRolePolicy",
        "iam:ListAttachedRolePolicies",
        "iam:ListInstanceProfilesForRole",
        "iam:ListRolePolicies",
        "iam:PassRole"
      ],
      "Resource": [
        "arn:aws:iam::{aws_account_id}:role/{resource_prefix}-*",
        "arn:aws:iam::{aws_account_id}:role/mongodb-atlas-*"
      ]
    },
    {
      "Sid": "KmsCreate1",
      "Effect": "Allow",
      "Action": ["kms:TagResource"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "KmsManage2",
      "Effect": "Allow",
      "Action": [
        "kms:DescribeKey",
        "kms:EnableKeyRotation",
        "kms:GetKeyPolicy",
        "kms:GetKeyRotationStatus",
        "kms:ListResourceTags",
        "kms:ScheduleKeyDeletion"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "KmsRead3",
      "Effect": "Allow",
      "Action": [
        "kms:CreateAlias",
        "kms:CreateKey",
        "kms:DeleteAlias",
        "kms:ListAliases"
      ],
      "Resource": "*"
    },
    {
      "Sid": "LogsCreate1",
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "LogsRead2",
      "Effect": "Allow",
      "Action": [
        "logs:DeleteLogGroup",
        "logs:DescribeLogGroups",
        "logs:ListTagsForResource",
        "logs:PutRetentionPolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Route53Read1",
      "Effect": "Allow",
      "Action": ["route53:AssociateVPCWithHostedZone"],
      "Resource": "*"
    },
    {
      "Sid": "S3Read1",
      "Effect": "Allow",
      "Action": [
        "s3:AbortMultipartUpload",
        "s3:CreateBucket",
        "s3:DeleteBucket",
        "s3:DeleteObject",
        "s3:DeleteObjectVersion",
        "s3:GetAccelerateConfiguration",
        "s3:GetBucketAcl",
        "s3:GetBucketCORS",
        "s3:GetBucketLogging",
        "s3:GetBucketObjectLockConfiguration",
        "s3:GetBucketPolicy",
        "s3:GetBucketPublicAccessBlock",
        "s3:GetBucketRequestPayment",
        "s3:GetBucketTagging",
        "s3:GetBucketVersioning",
        "s3:GetBucketWebsite",
        "s3:GetEncryptionConfiguration",
        "s3:GetLifecycleConfiguration",
        "s3:GetObject",
        "s3:GetObjectTagging",
        "s3:GetObjectVersion",
        "s3:GetReplicationConfiguration",
        "s3:ListBucket",
        "s3:ListBucketVersions",
        "s3:ListTagsForResource",
        "s3:PutBucketPublicAccessBlock",
        "s3:PutBucketTagging",
        "s3:PutBucketVersioning",
        "s3:PutEncryptionConfiguration",
        "s3:PutLifecycleConfiguration",
        "s3:PutObject",
        "s3:PutObjectTagging"
      ],
      "Resource": [
        "arn:aws:s3:::{resource_prefix}-*",
        "arn:aws:s3:::{resource_prefix}-*/*"
      ]
    },
    {
      "Sid": "SecretsManagerCreate1",
      "Effect": "Allow",
      "Action": ["secretsmanager:CreateSecret", "secretsmanager:TagResource"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "SecretsManagerManage2",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:DeleteSecret",
        "secretsmanager:DescribeSecret",
        "secretsmanager:GetResourcePolicy",
        "secretsmanager:GetSecretValue",
        "secretsmanager:PutSecretValue"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "StsRead1",
      "Effect": "Allow",
      "Action": ["sts:GetCallerIdentity"],
      "Resource": "*"
    },
    {
      "Sid": "WafCreate1",
      "Effect": "Allow",
      "Action": ["wafv2:TagResource"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "WafManage2",
      "Effect": "Allow",
      "Action": [
        "wafv2:DeleteWebACL",
        "wafv2:GetWebACL",
        "wafv2:ListTagsForResource"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Example": "atlas-aws-chatbot"
        }
      }
    },
    {
      "Sid": "WafRead3",
      "Effect": "Allow",
      "Action": ["wafv2:CreateWebACL"],
      "Resource": "*"
    }
  ]
}
```

## Split it per service

A bundle this size exceeds the 6,144-character managed-policy limit. Two ways to attach it:

- **Inline policy.** Minify the JSON and attach it as one inline policy on the deployer role. The full bundle is about 9.7 KB without the formatting whitespace and the minimal bundle about 8.9 KB, both under the 10,240-character role inline limit.
- **Managed policies.** Split the bundle by service, one `aws_iam_policy` per service, and attach each to the role. A per-service file stays well under the limit, and a failure names the service.

The IAM statements need two extra constraints when Terraform manages the role:

- Scope the role actions to the role-name prefixes: `role/{resource_prefix}-*` for the app roles and `role/mongodb-atlas-*` for the shared role the `atlas-aws` module creates.
- Limit `iam:AttachRolePolicy` to an allowlist: `policy/{resource_prefix}-*` plus the AWS-managed `service-role/AmazonECSTaskExecutionRolePolicy` that the module attaches to the ECS execution role.

Both bundles already carry those constraints in the `IamRole*` statements.

## Close the IAM escalation

A deployer that can call `iam:CreateRole` and `iam:AttachRolePolicy` can create a role and attach `AdministratorAccess` to it. The role-name prefix limits where the role lands. It does not limit what the role can do.

Set `overrides.permissions_boundary` to close that path:

```hcl
module "chatbot" {
  # ...
  overrides = {
    permissions_boundary = "arn:aws:iam::{aws_account_id}:policy/{resource_prefix}-permissions-boundary"
  }
}
```

The module then attaches the boundary to every role it creates, so a role it creates can do its job but cannot grant itself more. A permissions boundary must allow an action for the entity to perform it, because the effective permissions are the intersection of the identity policy and the boundary. A deny-only boundary would allow nothing, so the boundary allows every action and denies the escalation set:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "AllowAll", "Effect": "Allow", "Action": "*", "Resource": "*" },
    {
      "Sid": "DenyIamEscalation",
      "Effect": "Deny",
      "Action": ["iam:*", "organizations:*", "account:*"],
      "Resource": "*"
    }
  ]
}
```

Two conditions on the deployer policy make the boundary mandatory:

- `iam:CreateRole` carries `Condition: { "StringEquals": { "iam:PermissionsBoundary": "<boundary arn>" } }`. A create without the boundary is denied.
- `iam:PutRolePermissionsBoundary` joins the allowed actions, so the module can attach the boundary in the same flow.

Both bundles carry these conditions. Create the boundary policy first, then set its ARN.

## Exceptions

Some actions cannot use a tag condition. Each stays on `"*"` with no condition, because AWS authorizes it against a resource that carries no tag of its own, or does not evaluate a tag on the call.

- **`wafv2:CreateWebACL`**: the create runs before the tag exists in the authorization context.
- **`cloudfront:GetVpcOrigin`, `GetDistribution`, `ListTagsForResource`**: CloudFront does not evaluate `aws:ResourceTag` on these reads.
- **`codebuild:BatchGetBuilds`, `BatchGetProjects`**: CodeBuild does not evaluate `aws:ResourceTag` on these reads.
- **`kms:CreateAlias`, `DeleteAlias`**: KMS aliases are not tagged.
- **`ec2:DisassociateAddress`, `DisassociateRouteTable`**: the EIP and route-table associations carry no tag of their own.
- **`logs:PutRetentionPolicy`, `DeleteLogGroup`, `ListTagsForResource`**: CloudWatch Logs does not evaluate `aws:ResourceTag` for these.

S3 scopes by name prefix instead of tag, because `s3:CreateBucket` carries no tags in the request. Its statement uses `arn:aws:s3:::{resource_prefix}-*` and `arn:aws:s3:::{resource_prefix}-*/*`.

One classification is easy to get wrong: `secretsmanager:DeleteSecret` is a delete, not a create, so it sits with the manage actions under `aws:ResourceTag`, not under `aws:RequestTag`.

## Capture your own

The bundles come from a live capture of the module's own API calls. To capture the calls for your version of the module:

1. Record the calls with an [iamlive](https://github.com/iann0036/iamlive) proxy in front of Terraform.
2. Run all three lifecycle phases through the proxy: `terraform destroy`, then `terraform apply`, then `terraform plan`.
3. Turn the captured actions into per-service policy JSON, then combine or attach them as above.

The three phases each contribute actions the others miss. A destroy records the `Delete*`, `Detach*`, and `Revoke*` calls. An apply records the `Create*`, `Put*`, and `Attach*` calls. A plan records the `Describe*`, `List*`, and `Get*` reads. A create-only capture misses every delete.

Lesson from the first capture: the destroy path surfaced five actions the apply never called (`elasticloadbalancing:DeleteRule`, `DeleteListener`, `cloudfront:GetDistribution`, `ec2:DisassociateAddress`, `secretsmanager:DeleteSecret`). Run destroy before apply, and re-run until both are clean.

The proxy misses a few actions silently, so verify the capture before you trust it: compare the captured service list against the resource types in the stack, and check the proxy debug log for calls it saw but did not map.
